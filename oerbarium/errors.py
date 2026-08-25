class ClientError(Exception):
    """Errors returning form the LLM API Client."""

class ConfigurationError(ClientError):
    """Configuration errors."""

class ParsingError(ClientError):
    """The LLM reply could not be turned into valid metadata."""

class ToolError(ClientError):
    """A tool could not answer the LLM's request."""

class InputError(ClientError):
    """The input file cannot be read as OER records."""

class CrawlError(ClientError):
    """A resource page could not be fetched or parsed."""
