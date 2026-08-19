import os
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigurationError

ENV_FILE = "config.env"
DEFAULT_BASE_URL = "https://maki.uni-mannheim.de/v1"
MAKI_API_KEY = "MAKI_API_KEY"
API_BASE_URL = "API_BASE_URL"
MODEL_NAME = "MODEL_NAME"


def resolve_api_key(explicit: str | None = None, env_file: str = ENV_FILE) -> str:
    """Find the API key in the explicit argument, the environment, or config.env."""
    if explicit:
        return explicit
    if key := os.getenv(MAKI_API_KEY):
        return key

    load_dotenv(env_file)
    if key := os.getenv(MAKI_API_KEY):
        return key

    raise ConfigurationError(
        f"No API key found. Set the {MAKI_API_KEY} environment variable, "
        f"put {MAKI_API_KEY}=... in {Path(env_file).resolve()}, "
        "or pass --api-key."
    )


def resolve_base_url(env_file: str = ENV_FILE) -> str:
    """Find the API endpoint in the environment or config.env."""
    if url := os.getenv(API_BASE_URL):
        return url
    load_dotenv(env_file)
    return os.getenv(API_BASE_URL) or DEFAULT_BASE_URL


def resolve_model_name(explicit: str | None = None, env_file: str = ENV_FILE) -> str:
    """Find the LLM model name in the explicit argument or config.env."""
    if explicit:
        return explicit
    if model_name := os.getenv(MODEL_NAME):
        return model_name

    load_dotenv(env_file)
    return os.getenv(MODEL_NAME)
