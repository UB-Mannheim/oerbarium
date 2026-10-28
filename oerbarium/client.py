import json
import logging
import re

from openai import APIError, OpenAI
from pydantic import ValidationError

from .config import (
    API_KEY_ENV_VAR,
    LLM_MAX_RETRIES,
    LLM_MAX_TOOL_ROUNDS,
    LLM_TIMEOUT_SECONDS,
    LLM_USE_STRUCTURED_OUTPUT,
    MODEL_NAME_ENV_VAR,
)
from .errors import ClientError, ConfigurationError, ParsingError
from .prompts import DEFAULT_SYSTEM_PROMPT
from .schema import DaliaInterchangeFormat
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LlmClient:
    """OpenAI compatible API client for querying LLMs."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        tools: ToolRegistry | None = None,
        timeout: float = LLM_TIMEOUT_SECONDS,
        max_retries: int = LLM_MAX_RETRIES,
        max_tool_rounds: int = LLM_MAX_TOOL_ROUNDS,
        use_structured_output: bool = LLM_USE_STRUCTURED_OUTPUT,
    ):
        if not api_key:
            raise ConfigurationError(
                f"API key is empty. Set {API_KEY_ENV_VAR} or pass --api-key."
            )
        if not model_name:
            raise ConfigurationError(
                f"No model name given. Set {MODEL_NAME_ENV_VAR} or pass --model-name."
            )
        self._base_url = base_url
        self._timeout = timeout
        self._model_name = model_name
        self._tools = tools if tools is not None else ToolRegistry()
        self._max_tool_rounds = max_tool_rounds
        self._use_structured_output = use_structured_output
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
        )

    def call(
        self,
        user_prompt: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> DaliaInterchangeFormat:
        """
        Extract the metadata of one OER, answering the model's tool calls.
        """
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for _ in range(self._max_tool_rounds):
            message = self._complete(messages)
            if not message.tool_calls:
                return self._to_metadata(message.content)

            messages.append(message.model_dump(exclude_none=True))
            for tool_call in message.tool_calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": self._tools.dispatch(
                            tool_call.function.name, tool_call.function.arguments
                        ),
                    }
                )

        raise ParsingError(
            f"The model kept calling tools after {self._max_tool_rounds} rounds "
            "without returning metadata."
        )

    def _complete(self, messages: list[dict]):
        """
        One request to the chat completions endpoint.
        """
        kwargs: dict = {"model": self._model_name, "messages": messages}
        if tools := self._tools.schemas():
            kwargs["tools"] = tools
        if self._use_structured_output:
            kwargs["response_format"] = DaliaInterchangeFormat.response_format()

        try:
            response = self._client.chat.completions.create(**kwargs)
        except APIError as exc:
            raise ClientError(f"API request to {self._base_url} failed: {exc}") from exc
        return response.choices[0].message

    def _to_metadata(self, content: str | None) -> DaliaInterchangeFormat:
        """
        Validate the model's final answer against the metadata schema.
        """
        if not content:
            raise ParsingError("The model returned an empty answer.")
        raw = CODE_FENCE.sub("", THINK_BLOCK.sub("", content)).strip()
        try:
            return DaliaInterchangeFormat.model_validate(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ParsingError(f"Answer is not valid JSON: {exc}\n{raw}") from exc
        except ValidationError as exc:
            raise ParsingError(f"Answer does not match the schema: {exc}\n{raw}") from exc
