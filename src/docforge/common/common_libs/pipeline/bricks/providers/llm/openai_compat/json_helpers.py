# ====== Code Summary ======
# OpenAICompatJsonHelpers — static request/response helpers for structured JSON generation on an
# OpenAI-compatible chat endpoint. Splits the request-body builders (native ``response_format`` and
# the tool-calling fallback), the content extraction (incl. refusal detection), and a lightweight
# schema validation out of OpenAICompatLLMProvider so the provider file stays under the line budget.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# Tool name used by the tool-calling fallback path. A single function whose parameters ARE the
# requested JSON schema — servers without ``response_format`` still emit schema-bound JSON this way.
_TOOL_NAME = "emit_metadata"


class OpenAICompatJsonHelpers:
    """
    Static helpers for OpenAI-compatible structured JSON generation.

    Covers two request shapes (native ``response_format=json_schema`` and a tool-calling
    fallback), response content extraction with refusal detection, and a cheap structural
    validation (object shape + required-key presence). No I/O — the provider owns the HTTP call.
    """

    logger = loggerplusplus.bind(identifier="OpenAICompatJsonHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("OpenAICompatJsonHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_json_schema_payload(
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """
        Build a chat-completions body using the native ``response_format=json_schema`` mode.

        Args:
            model (str): Model identifier.
            messages (list): Chat messages (the reask loop appends correction turns here).
            schema (dict): The strict JSON schema the response must satisfy.
            max_tokens (int): Token budget.
            temperature (float): Sampling temperature.

        Returns:
            dict: The request body for ``POST /chat/completions``.
        """
        return {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "metadata", "strict": True, "schema": schema},
            },
        }

    @staticmethod
    def build_tool_payload(
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """
        Build a chat-completions body using a single forced tool call as a JSON-schema fallback.

        For OpenAI-compatible servers that do not implement ``response_format``: the requested
        schema becomes the tool's ``parameters`` and the model is forced to call it, so the
        arguments are schema-bound JSON.

        Args:
            model (str): Model identifier.
            messages (list): Chat messages.
            schema (dict): The JSON schema (used as the tool's parameter schema).
            max_tokens (int): Token budget.
            temperature (float): Sampling temperature.

        Returns:
            dict: The request body for ``POST /chat/completions``.
        """
        return {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": _TOOL_NAME,
                        "description": "Return the extracted metadata as structured JSON.",
                        "parameters": schema,
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": _TOOL_NAME}},
        }

    @staticmethod
    def extract_content(response_json: dict[str, Any]) -> str:
        """
        Extract the assistant message content from a ``response_format`` response.

        Args:
            response_json (dict): Parsed OpenAI-compatible response.

        Returns:
            str: The raw JSON string in ``choices[0].message.content``.

        Raises:
            ValueError: When the model returned a refusal instead of content.
            KeyError: When the response shape is missing the expected fields.
        """
        message = response_json["choices"][0]["message"]
        # 1. Structured-output servers expose a dedicated ``refusal`` field — honor it explicitly.
        refusal = message.get("refusal")
        if refusal:
            raise ValueError(f"model refused to answer: {refusal}")
        return message["content"] or ""

    @staticmethod
    def extract_tool_args(response_json: dict[str, Any]) -> str:
        """
        Extract the tool-call arguments JSON string from a tool-calling response.

        Args:
            response_json (dict): Parsed OpenAI-compatible response.

        Returns:
            str: The ``arguments`` JSON string of the first tool call.

        Raises:
            KeyError / IndexError: When no tool call is present in the response.
        """
        tool_calls = response_json["choices"][0]["message"]["tool_calls"]
        return tool_calls[0]["function"]["arguments"] or ""

    @staticmethod
    def missing_required_keys(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
        """
        Return the schema-required top-level keys absent from ``data`` (cheap structural check).

        Full JSON-schema validation is intentionally avoided — the schema is built by
        ``MetagenSchemaBuilder`` (strict, root-object). A present-keys check is enough to drive
        the reask loop without pulling in a validator dependency.

        Args:
            data (dict): The parsed response object.
            schema (dict): The strict JSON schema sent to the model.

        Returns:
            list[str]: Required keys that are missing (empty when the object is complete).
        """
        required = schema.get("required", []) or []
        return [key for key in required if key not in data]

    @staticmethod
    def is_response_format_unsupported(status_code: int, body: str) -> bool:
        """
        Heuristically detect that a server rejected the native ``response_format`` mode.

        A 400/422 mentioning ``response_format`` / ``json_schema`` is treated as "this server does
        not support structured outputs" → the caller retries once via the tool-calling fallback.

        Args:
            status_code (int): HTTP status of the failed request.
            body (str): Response body text.

        Returns:
            bool: True when the failure looks like an unsupported-feature rejection.
        """
        if status_code not in (400, 422):
            return False
        lowered = body.lower()
        return "response_format" in lowered or "json_schema" in lowered
