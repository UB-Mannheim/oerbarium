import json
import logging

from .base import LlmTool
from .metadata_tools import ExplainFieldTool, GetPicklistTool, LookupDisciplineTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    The set of tools offered to the LLM. The client only ever talks to this registry,
    so adding a tool means adding an `LlmTool` subclass here — no change to the client or the CLI.
    """

    def __init__(self, tools: list[LlmTool] | None = None):
        self._tools = {tool.name: tool for tool in tools or []}

    @classmethod
    def default(cls) -> "ToolRegistry":
        """
        Registry with every metadata lookup tool wired to its resource.
        """
        return cls(
            [LookupDisciplineTool(), GetPicklistTool(), ExplainFieldTool()]
        )

    def schemas(self) -> list[dict] | None:
        """
        Tool definitions for the API, or None when there are no tools.
        """
        if not self._tools:
            return None
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def dispatch(self, name: str, arguments: str) -> str:
        """
        Run the requested tool and return its reply for the tool message.

        Failures come back as content, not exceptions: a tool call the model
        got wrong should let it correct itself, not abort the whole run.
        """
        tool = self._tools.get(name)
        if tool is None:
            logger.debug("Unknown tool requested: %s", name)
            return json.dumps(
                {"error": f"Unknown tool '{name}'.", "available": list(self._tools)}
            )
        try:
            parsed = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as exc:
            logger.debug("Malformed arguments for %s: %s", name, arguments)
            return json.dumps({"error": f"Arguments are not valid JSON: {exc}"})

        logger.debug("Tool call %s(%s)", name, parsed)
        try:
            return tool.run(**parsed)
        except Exception as exc:  # a broken tool must not kill the run
            logger.debug("Tool %s failed: %s", name, exc)
            return json.dumps({"error": f"Tool '{name}' failed: {exc}"})
