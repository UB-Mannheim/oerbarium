import json
import logging
from collections import Counter
from pathlib import Path

import click

from .catalogue import (
    CatalogueMerger,
    Duplicate,
    backup_catalogue,
    read_parsed,
)
from .client import LlmClient
from .config import (
    DEFAULT_CATALOGUE_PATH,
    DEFAULT_PARSE_OUTPUT_FORMAT,
    LOG_FORMAT,
    MODEL_NAME_ENV_VAR,
    resolve_api_key,
    resolve_base_url,
    resolve_model_name,
)
from .crawler import DariahCrawler, read_url_list
from .errors import ClientError, ConfigurationError
from .schema import DaliaInterchangeFormat
from .service import (
    DaliaInterchangeFormatParser,
    ResultWriter,
    atomic_write_text,
    normalize_title,
    read_snapshot,
    record_source_for,
)
from .tools import ToolRegistry


class CrawlingProgressReporter:
    def report(self, number: int, total: int) -> None:
        click.echo(f"[{number}/{total}] Crawling website(s) ...")


class ParsingProgressReporter:
    def report(self, number: int, total: int) -> None:
        click.echo(f"[{number}/{total}] Parsing metadata into DIF V1.4 ...")


class DefinitionOrderGroup(click.Group):
    """Lists subcommands in the order they are defined, not alphabetically."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands)


@click.group(cls=DefinitionOrderGroup, no_args_is_help=True)
def cli() -> None:
    """
    🌳 Collect, parse and map Open Educational Resources (OER) metadata into
    the DALIA Interchange Format (DIF V1.4).
    """


@cli.group(no_args_is_help=True)
def crawl() -> None:
    """
    Collect raw OER metadata from a source site.
    """


@crawl.command("dariah", no_args_is_help=True)
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="URLs to crawl (.txt = one URL per line).",
)
@click.option(
    "-o",
    "--output-path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Where to write the crawled metadata as a JSON array.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Abort on the first failing URL instead of skipping it.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Log progress and skipped URLs."
)
def crawl_dariah(
    input_path: Path,
    output_path: Path,
    strict: bool,
    verbose: bool,
) -> None:
    """
    Crawl DARIAH-Campus resource pages into a JSON array.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format=LOG_FORMAT,
    )

    try:
        urls = read_url_list(input_path)
        records = DariahCrawler(
            strict=strict, reporter=CrawlingProgressReporter()
        ).crawl(urls)
    except (ClientError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise click.Abort() from exc
        raise click.ClickException(str(exc)) from exc

    if not records:
        raise click.ClickException("No resource could be crawled.")

    atomic_write_text(
        output_path, json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    )

    if skipped := len(urls) - len(records):
        click.echo(f"Skipped {skipped} of {len(urls)} URL(s)", err=True)
    click.echo(f"Wrote metadata of {len(records)} website(s) to {output_path}")


@cli.command("parse", no_args_is_help=True)
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Messy OER metadata to parse "
        "(.txt = one OER, .json = one per list item, .jsonl = one per line)."
    ),
)
@click.option(
    "-o",
    "--output-path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Where to write the parsed metadata as a JSON array, rewritten after every record.",
)
@click.option(
    "-f",
    "--format",
    type=click.Choice(["json", "tsv"]),
    default=DEFAULT_PARSE_OUTPUT_FORMAT,
    show_default=True,
    help="Data format of the parsed output file.",
)
@click.option(
    "-m",
    "--model-name",
    default=None,
    help="LLM model name."
)
@click.option(
    "-b",
    "--base-url",
    default=None,
    help="API base URL."
)
@click.option(
    "--api-key",
    default=None,
    help="API key."
)
@click.option(
    "--resume",
    is_flag=True,
    help="Continue an interrupted run: keep the records already in the output file "
    "and parse only the ones missing from it. Records are matched by title, so a "
    "record the model retitled is parsed again.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Abort on the first failing record instead of skipping it. "
    "Records parsed before the failure stay in the output file.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Log progress and tool calls."
)
def parse_oer(
    input_path: Path,
    output_path: Path,
    format: str,
    model_name: str | None,
    base_url: str | None,
    api_key: str | None,
    resume: bool,
    strict: bool,
    verbose: bool,
) -> None:
    """
    Parse messy OER metadata into DIF V1.4.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format=LOG_FORMAT,
    )

    existing: list[DaliaInterchangeFormat] = []
    writer = ResultWriter(output_path, format=format)
    try:
        if resume:
            existing = read_snapshot(output_path, format=format)
            writer = ResultWriter(output_path, format=format, existing=existing)
            if existing:
                click.echo(f"Resuming from {len(existing)} record(s) in {output_path}")
        skip_keys = Counter(normalize_title(record.Title) for record in existing)

        source = record_source_for(input_path)
        client = LlmClient(
            api_key=resolve_api_key(api_key),
            model_name=_require_model_name(model_name),
            base_url=base_url or resolve_base_url(),
            tools=ToolRegistry.default(),
        )
        DaliaInterchangeFormatParser(
            client, strict=strict, reporter=ParsingProgressReporter()
        ).parse(source, sink=writer, skip_keys=skip_keys)
    except (ClientError, KeyboardInterrupt) as exc:
        if writer.count:
            click.echo(f"Kept {writer.count} record(s) in {output_path}", err=True)
        if isinstance(exc, KeyboardInterrupt):
            raise click.Abort() from exc
        raise click.ClickException(str(exc)) from exc

    added = writer.count - writer.resumed_count
    if not writer.count:
        raise click.ClickException("No record could be parsed.")
    if not added:
        click.echo(f"Nothing left to parse: {writer.count} record(s) in {output_path}")
        return

    click.echo(f"Wrote {writer.count} record(s) to {output_path} ({added} new)")


@cli.command("merge", no_args_is_help=True)
@click.option(
    "-i",
    "--input",
    "input_paths",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    multiple=True,
    required=True,
    help="Parsed metadata to merge (.json or .tsv from `parse`). Repeat for several files.",
)
@click.option(
    "-c",
    "--catalogue",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_CATALOGUE_PATH,
    show_default=True,
    help="The OER catalogue (.xlsx) to merge into.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Merge records even when they are already in the catalogue "
    "(same Link, or same Title and Authors).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Log every merged row."
)
def merge_oer(
    input_paths: tuple[Path, ...],
    catalogue: Path,
    force: bool,
    verbose: bool,
) -> None:
    """
    Merge parsed DIF V1.4 metadata into the OER catalogue (.xlsx).
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format=LOG_FORMAT,
    )

    try:
        records = [record for path in input_paths for record in read_parsed(path)]
        merger = CatalogueMerger(catalogue)
        plan = merger.plan(records, force=force)

        for duplicate in plan.skipped:
            _warn_duplicate(duplicate, "skipped. Use --force to merge anyway.")
        for duplicate in plan.forced:
            _warn_duplicate(duplicate, "merged anyway (--force).")

        if not plan.to_write:
            click.echo(f"Nothing to merge: all {len(records)} record(s) are already in {catalogue}")
            return

        backup = backup_catalogue(catalogue)
        click.echo(f"Backed up catalogue to {backup}")
        report = merger.write(plan)
    except (ClientError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise click.Abort() from exc
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"Merged {report.count} record(s) into {catalogue} "
        f"(rows {report.first_row}-{report.last_row}), "
        f"skipped {len(plan.skipped)} duplicate(s)"
    )
    click.echo(f"Validation passed: {report.count} new row(s) in the right columns, existing rows unchanged")


def _warn_duplicate(duplicate: Duplicate, outcome: str) -> None:
    record = duplicate.record
    click.echo(
        f'Warning: "{record.metadata.Title}" ({record.label}) duplicates '
        f"{duplicate.found_at} (matched on {duplicate.matched_on}) - {outcome}",
        err=True,
    )


def _require_model_name(explicit: str | None) -> str:
    """Resolve the model name, failing loudly when none is configured."""
    if model_name := resolve_model_name(explicit):
        return model_name
    raise ConfigurationError(
        f"No model name found. Set {MODEL_NAME_ENV_VAR} in the environment or config.env, "
        "or pass --model-name."
    )


def main() -> None:
    """Entry point of the `oer-cat` command."""
    cli()
