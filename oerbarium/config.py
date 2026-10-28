import os
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigurationError

ENV_FILE_PATH = "config.env"
API_KEY_ENV_VAR = "API_KEY"
API_BASE_URL_ENV_VAR = "API_BASE_URL"
MODEL_NAME_ENV_VAR = "MODEL_NAME"
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

# LLM Client
LLM_TIMEOUT_SECONDS = 180.0
LLM_MAX_RETRIES = 1
LLM_MAX_TOOL_ROUNDS = 5  # Rounds of tool calls before the model has to answer
LLM_USE_STRUCTURED_OUTPUT = True

# LLM Tools
METADATA_PACKAGE = "oerbarium.metadata"
HFS_MAPPING_FILENAME = "hochschulfaechersystematik_mapping.json"
PICKLISTS_FILENAME = "metadata_picklists.json"
FIELD_EXPLANATIONS_FILENAME = "metadata_explanation.json"
DISCIPLINE_LOOKUP_MAX_HITS = 5

# Crawler
CRAWL_TIMEOUT_SECONDS = 30.0

# Parser
DEFAULT_PARSE_OUTPUT_FORMAT = "json"

# OER Catalogue for merging parsed metadata
DEFAULT_CATALOGUE_PATH = Path("data/catalogue/AiDaLi_OER_Katalog.xlsx")
CATALOGUE_SHEET_NAME = "OER_Catalogue"
CATALOGUE_BACKUP_DIR_NAME = ".backup"


def resolve_api_key(explicit: str | None = None) -> str:
    """
    Find the API key in the explicit argument or the environment — never in
    config.env, so the key is not stored in a file next to the project.
    """
    if explicit:
        return explicit
    if key := os.getenv(API_KEY_ENV_VAR):
        return key

    raise ConfigurationError(
        f"No API key found. Set the {API_KEY_ENV_VAR} environment variable "
        "or pass --api-key."
    )


def resolve_base_url(env_file: str = ENV_FILE_PATH) -> str:
    """Find the API endpoint in the environment or config.env."""
    if url := os.getenv(API_BASE_URL_ENV_VAR):
        return url
    load_dotenv(env_file)
    return os.getenv(API_BASE_URL_ENV_VAR)


def resolve_model_name(explicit: str | None = None, env_file: str = ENV_FILE_PATH) -> str:
    """Find the LLM model name in the explicit argument or config.env."""
    if explicit:
        return explicit
    if model_name := os.getenv(MODEL_NAME_ENV_VAR):
        return model_name

    load_dotenv(env_file)
    return os.getenv(MODEL_NAME_ENV_VAR)
