from abc import ABC, abstractmethod


class LlmTool(ABC):
    """
    A single tool the LLM may call while extracting metadata.

    Subclasses declare their `name`, `description` and argument schema; the
    OpenAI wire format is derived from those, so tools never repeat it.
    """

    name: str
    description: str

    @abstractmethod
    def parameters(self) -> dict:
        """JSON schema of the tool's arguments."""

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool and return the content of the tool message."""

    def to_openai_schema(self) -> dict:
        """This tool as an entry of the API's `tools` argument."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }
