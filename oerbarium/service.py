import csv
import io
import json
import logging
import os
import re
import string
import tempfile
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from .errors import ClientError, InputError
from .schema import DaliaInterchangeFormat

logger = logging.getLogger(__name__)


class MetadataExtractor(Protocol):
    """What the parser needs from an LLM client — nothing more."""

    def call(self, user_prompt: str) -> DaliaInterchangeFormat: ...


class ProgressReporter(Protocol):
    """Notified as records are processed — display concerns live outside this module."""

    def report(self, number: int, total: int) -> None: ...


class NullProgressReporter:
    """Default reporter: does nothing."""

    def report(self, number: int, total: int) -> None:
        pass


class ResultSink(Protocol):
    """Receives each record as soon as it is parsed."""

    def append(self, record: DaliaInterchangeFormat) -> None: ...


class NullResultSink:
    """Default sink: does nothing."""

    def append(self, record: DaliaInterchangeFormat) -> None:
        pass


def atomic_write_text(path: Path, text: str) -> None:
    """
    Replace `path` with `text` in one step — readers see the old or the new file,
    never a partial one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def normalize_title(value: str) -> str:
    """
    A title reduced to what two spellings of the same title share: case, inner
    whitespace and surrounding punctuation are ignored.
    """
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed.strip(string.punctuation + string.whitespace).casefold()


def resume_key(raw_record: str) -> str | None:
    """
    The title a raw input record can be recognised by, or None when it has none
    — such a record can never be matched against a snapshot and is always parsed.
    """
    try:
        data = json.loads(raw_record)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    for wanted in ("title", "name"):
        for key, value in data.items():
            if key.lower() == wanted and isinstance(value, str) and value.strip():
                return normalize_title(value)
    return None


def read_snapshot(path: Path, format: str = "json") -> list[DaliaInterchangeFormat]:
    """
    The records an earlier run already wrote to `path`, or none when there is
    nothing to resume from.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    rows = _read_tsv_rows(text, path) if format == "tsv" else _read_json_rows(text, path)
    try:
        return [DaliaInterchangeFormat.model_validate(row) for row in rows]
    except ValidationError as exc:
        raise InputError(f"{path} is not a DIF V1.4 snapshot: {exc}") from exc


def _read_json_rows(text: str, path: Path) -> list[dict]:
    """The objects of a JSON snapshot."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise InputError(f"{path} does not hold a JSON array of records.")
    return data


def _read_tsv_rows(text: str, path: Path) -> list[dict]:
    """The rows of a TSV snapshot, with empty cells back as None."""
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    fields = DaliaInterchangeFormat.model_fields
    if reader.fieldnames != list(fields):
        raise InputError(
            f"{path} does not carry the DIF V1.4 header. "
            f"Expected: {', '.join(fields)}."
        )
    optional = {name for name, field in fields.items() if not field.is_required()}
    return [
        {key: (None if key in optional and not value else value) for key, value in row.items()}
        for row in reader
    ]


class RecordSource(ABC):
    """A file holding one or more messy OER records."""

    def __init__(self, path: Path):
        self._path = path

    @abstractmethod
    def read(self) -> list[str]:
        """The raw records, one string per OER."""


class TextRecordSource(RecordSource):
    """A plain text file: the whole file describes a single OER."""

    def read(self) -> list[str]:
        text = self._path.read_text(encoding="utf-8").strip()
        if not text:
            raise InputError(f"{self._path} is empty.")
        return [text]


class JsonRecordSource(RecordSource):
    """A JSON file: a list of records, or a single object."""

    def read(self) -> list[str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputError(f"{self._path} is not valid JSON: {exc}") from exc

        records = data if isinstance(data, list) else [data]
        if not records:
            raise InputError(f"{self._path} contains no records.")
        return [json.dumps(record, ensure_ascii=False, indent=2) for record in records]


class JsonLinesRecordSource(RecordSource):
    """A JSON Lines file: one record per non-empty line."""

    def read(self) -> list[str]:
        records = []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise InputError(
                    f"{self._path} line {number} is not valid JSON: {exc}"
                ) from exc

        if not records:
            raise InputError(f"{self._path} contains no records.")
        return [json.dumps(record, ensure_ascii=False, indent=2) for record in records]


def record_source_for(path: Path) -> RecordSource:
    """
    Pick the source matching the file's suffix.
    """
    sources = {
        ".txt": TextRecordSource,
        ".json": JsonRecordSource,
        ".jsonl": JsonLinesRecordSource,
    }
    source = sources.get(path.suffix.lower())
    if source is None:
        raise InputError(
            f"Unsupported input '{path.suffix}'. Use one of: {', '.join(sources)}."
        )
    return source(path)


class ResultWriter:
    """
    Writes parsed metadata as a JSON array, rewritten atomically after every record.
    """

    def __init__(
        self,
        path: Path,
        format: str = "json",
        existing: list[DaliaInterchangeFormat] | None = None,
    ):
        self._format = format
        self._path = path
        self._records: list[DaliaInterchangeFormat] = list(existing or [])
        self._resumed_count = len(self._records)

    @property
    def count(self) -> int:
        """How many records are currently on disk."""
        return len(self._records)

    @property
    def resumed_count(self) -> int:
        """How many records were already on disk when this writer took over."""
        return self._resumed_count

    def append(self, record: DaliaInterchangeFormat) -> None:
        """Add a record and rewrite the output file, so the run can be interrupted safely."""
        self._records.append(record)
        if self._format == "tsv":
            text = self._render_tsv()
        else:
            payload = [entry.model_dump() for entry in self._records]
            text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        atomic_write_text(self._path, text)

    def _render_tsv(self) -> str:
        fields = list(DaliaInterchangeFormat.model_fields)
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        for entry in self._records:
            row = entry.model_dump()
            writer.writerow(["" if row[field] is None else row[field] for field in fields])
        return buffer.getvalue()


class DaliaInterchangeFormatParser:
    """
    Turns the records of a source into validated metadata of type
    DALIA Interchange Format V1.4 (DIF V1.4).
    """

    def __init__(
        self,
        client: MetadataExtractor,
        strict: bool = False,
        reporter: ProgressReporter | None = None,
    ):
        self._client = client
        self._strict = strict
        self._reporter = reporter or NullProgressReporter()

    def parse(
        self,
        source: RecordSource,
        sink: ResultSink | None = None,
        skip_keys: Counter[str] | None = None,
    ) -> list[DaliaInterchangeFormat]:
        """
        Parse every record, one LLM call each, handing each result to `sink` as it lands.

        `skip_keys` counts the titles an earlier run already parsed: a title seen
        N times there skips the next N input records carrying it.
        """
        sink = sink or NullResultSink()
        records = self._remaining(source.read(), skip_keys)
        parsed: list[DaliaInterchangeFormat] = []
        for number, record in enumerate(records, start=1):
            logger.info("Parsing record %s/%s", number, len(records))
            self._reporter.report(number, len(records))
            try:
                metadata = self._client.call(record)
            except ClientError as exc:
                if self._strict:
                    raise
                logger.warning("Record %s failed, skipping: %s", number, exc)
                continue
            parsed.append(metadata)
            sink.append(metadata)
        return parsed

    def _remaining(
        self, records: list[str], skip_keys: Counter[str] | None
    ) -> list[str]:
        """
        The records still to parse: those whose title an earlier run has not
        already written out.
        """
        if not skip_keys:
            return records

        pending = Counter(skip_keys)
        remaining: list[str] = []
        skipped = 0
        untitled = 0
        for record in records:
            key = resume_key(record)
            if key is None:
                untitled += 1
            elif pending[key] > 0:
                pending[key] -= 1
                skipped += 1
                continue
            remaining.append(record)

        logger.info("Skipping %s record(s) already parsed", skipped)
        if untitled:
            logger.warning(
                "%s record(s) carry no title and are parsed again", untitled
            )
        return remaining
