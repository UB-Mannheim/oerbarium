import csv
import io
import json
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol

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


def record_source_for(path: Path) -> RecordSource:
    """
    Pick the source matching the file's suffix.
    """
    sources = {".txt": TextRecordSource, ".json": JsonRecordSource}
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

    def __init__(self, path: Path, format: str = "json"):
        self._format = format
        self._path = path
        self._records: list[DaliaInterchangeFormat] = []

    @property
    def count(self) -> int:
        """How many records are currently on disk."""
        return len(self._records)

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
        self, source: RecordSource, sink: ResultSink | None = None
    ) -> list[DaliaInterchangeFormat]:
        """
        Parse every record, one LLM call each, handing each result to `sink` as it lands.
        """
        sink = sink or NullResultSink()
        records = source.read()
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
