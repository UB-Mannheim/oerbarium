# AGENTS.md

Guidance for coding agents working on **OERbarium**, a Python CLI that collects
Open Educational Resource (OER) metadata, maps it into the
[DALIA Interchange Format (DIF V1.4)](https://doi.org/10.5281/zenodo.17871138)
with an LLM, and merges the result into an Excel catalogue. `README.md` is the
user-facing reference for every command and option.

## Setup and commands

- Python 3.13 (`.python-version`), managed with `uv`. Install with `uv sync`.
- Run the CLI with `uv run oerbarium <command>` (`crawl dariah`, `parse`, `merge`).
- Lint with `uvx ruff check .` (config in `pyproject.toml`; `BLE001` is ignored on
  purpose). Ruff is not a project dependency.
- There is no test suite yet. Check a change by running the affected command on a
  small input, e.g. a two-record `.json` for `parse`, or a copy of the catalogue
  passed with `-c` for `merge`.

## LLM configuration

`parse` talks to any OpenAI-compatible endpoint that supports **tool calling** and
structured output. `API_BASE_URL` and `MODEL_NAME` resolve in this order: CLI flag
→ environment variable → `config.env` in the working directory (see
`config.env.example`). `API_KEY` comes only from `--api-key` or the environment:
never add it to `config.env` or `config.env.example`, never read it from a file,
and never print or commit it.

## Architecture

```
cli.py           click commands; the only place that echoes to the terminal
crawler.py       DariahCrawler: fetches DARIAH-Campus pages (requests + bs4) into raw dicts
service.py       record sources (.txt/.json), DaliaInterchangeFormatParser, ResultWriter,
                 resume logic, atomic_write_text
client.py        LlmClient: chat completions loop, answers tool calls, validates the reply
schema.py        DaliaInterchangeFormat (pydantic): the 17 DIF fields, also the
                 strict JSON schema sent as response_format
prompts.py       DEFAULT_SYSTEM_PROMPT describing every field and its format
tools/           LlmTool base, ToolRegistry, metadata lookup tools offered to the model
resources.py     loaders for the JSON files in oerbarium/metadata/
catalogue.py     CatalogueMerger: duplicate detection, backup, xlsx write and validation
errors.py        ClientError and its subclasses
metadata/        packaged vocabularies (Hochschulfächersystematik, picklists, field docs)
```

Data flow: `crawl` → raw JSON array → `parse` → DIF JSON/TSV → `merge` → `data/AiDaLi_OER_Katalog.xlsx`.

## Conventions

- **Errors:** raise a `ClientError` subclass from `errors.py` (add one if none fits).
  The CLI catches `ClientError` and turns it into a `click.ClickException`; don't
  call `click` or `sys.exit` outside `cli.py`.
- **Output and logging:** library modules use `logging.getLogger(__name__)` and report
  progress through the `ProgressReporter` protocol. Only `cli.py` uses `click.echo`.
- **Dependencies via protocols:** the parser depends on `MetadataExtractor`,
  `ResultSink` and `ProgressReporter`, not on concrete classes. Keep new seams small
  in the same way, with a `Null*` default where it helps.
- **Skip vs. strict:** batch commands skip a failing item with a warning by default
  and re-raise under `--strict`. New batch features should behave the same way.
- **Safe writes:** write output files with `atomic_write_text`. `ResultWriter` rewrites
  the whole file after every record so an interrupted `parse` loses nothing and can
  continue with `--resume`.
- **Schema changes:** `DaliaInterchangeFormat` field names are the DIF keys and the
  catalogue column order (`No`, the DIF fields, `Publisher`). Changing a field means
  updating `schema.py`, `prompts.py`, the files in `metadata/` and the catalogue
  header check in `catalogue.py` together.
- **Adding an LLM tool:** subclass `LlmTool` in `tools/metadata_tools.py` (declare
  `name`, `description`, `parameters()`, `run()`) and register it in
  `ToolRegistry.default()`. Tools return JSON strings; `ToolRegistry.dispatch` turns
  failures into error content so the model can correct itself, so don't raise for
  bad model input.
- Multi-valued DIF fields are joined with `" * "`.
- Style: type hints everywhere (`str | None`, built-in generics), short docstrings that
  say why rather than how, `pathlib.Path` for files, UTF-8 and `ensure_ascii=False`
  for JSON.

## Data and files

- `data/AiDaLi_OER_Katalog.xlsx` is the real catalogue. Don't edit or `merge` into it
  while experimenting: pass a copy via `-c`. `merge` backs up to `data/.backup/` and
  validates before replacing the file, and those guarantees must stay intact.
  Ignore Excel lock files such as `~$AiDaLi_OER_Katalog.xlsx`.
- `output/`, `notebooks/`, `.backup/` and `*.env` are gitignored. Put scratch results
  in `output/`.
- `crawl_sites/` and `input/` hold crawl URL lists and sample inputs.

## Documentation

When you add or change a command or option, update the matching section and option
table in `README.md`.
