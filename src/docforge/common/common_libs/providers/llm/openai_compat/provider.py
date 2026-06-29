# ====== Code Summary ======
# OpenAICompatLLMProvider — ONE OpenAI-compatible chat-completions client for both local and
# external servers. Locality is a runtime flag: "external" (cloud OpenAI — api_key required)
# and "local" (vLLM/Ollama/llama.cpp — api_key usually "local") share the identical
# /chat/completions protocol. Replaces the former LocalLLMProvider + OpenAILLMProvider.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .json_helpers import OpenAICompatJsonHelpers

# Default cloud endpoint used when an external config omits base_url.
_DEFAULT_EXTERNAL_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatLLMProvider(LoggerClass):
    """
    LLM provider for any OpenAI ``/chat/completions`` server, local or external.

    Satisfies the ``LLMProvider`` protocol (``async generate``). The ``locality`` flag selects
    the deployment ("local" vs "external") and the auth policy (api_key required iff external).
    """

    def __init__(
        self,
        base_url: str,
        locality: str = "local",
        api_key: str = "local",
        model: str = "",
        max_tokens: int = 512,
        temperature: float = 0.0,
        json_max_retries: int = 2,
    ) -> None:
        """
        Initialize the OpenAI-compatible LLM provider.

        Args:
            base_url (str): Chat-completions base URL (cloud default applied for external).
            locality (str): "local" or "external" — sets the auth policy.
            api_key (str): Bearer token. Required (non-empty) when locality == "external".
            model (str): Model identifier sent in the request.
            max_tokens (int): Default maximum tokens to generate.
            temperature (float): Default sampling temperature.
            json_max_retries (int): Reask attempts for ``generate_json`` on parse/validation
                failure (in addition to the first attempt).

        Raises:
            ValueError: When locality == "external" and api_key is empty.
        """
        LoggerClass.__init__(self)
        if locality == "external" and not api_key:
            raise ValueError("OpenAICompatLLMProvider: api_key is required when locality='external'.")
        self._base_url = (base_url or (_DEFAULT_EXTERNAL_BASE_URL if locality == "external" else "")).rstrip("/")
        self._locality = locality
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._json_max_retries = json_max_retries
        self.logger.info(f"OpenAICompatLLMProvider initialized — locality={locality} url={self._base_url} model={self._model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """
        Generate a chat completion via the OpenAI-compatible endpoint.

        Args:
            prompt (str): Input prompt.
            max_tokens (int): Max tokens (overrides the instance default when non-zero).
            temperature (float): Sampling temperature (overrides the instance default when non-zero).

        Returns:
            str: The text of choices[0].message.content.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        # 1. Build the chat-completions request body
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature if temperature != 0.0 else self._temperature,
        }

        # 2. Send and parse the OpenAI-compatible response
        response_json = await self._post_chat(payload)
        return response_json["choices"][0]["message"]["content"]

    async def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """
        Generate a JSON object conforming to ``schema`` via OpenAI structured outputs.

        Tries the native ``response_format=json_schema`` mode first; on a server that rejects
        it (400/422 mentioning the feature) it falls back once to a forced tool call carrying the
        same schema. Each attempt runs through a bounded reask loop: a parse/validation failure is
        appended to the conversation and retried up to ``json_max_retries`` times. On final failure
        the chunk is never failed — an empty dict is returned (logged at WARNING).

        Args:
            prompt (str): Extraction instructions + content.
            schema (dict): Strict JSON schema the response must satisfy.
            max_tokens (int): Token budget (instance default when 0).
            temperature (float): Sampling temperature (instance default when 0).

        Returns:
            dict: The parsed object, or ``{}`` on final failure.
        """
        # 1. Seed the conversation; the reask loop appends correction turns onto it.
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        tokens = max_tokens or self._max_tokens
        temp = temperature if temperature != 0.0 else self._temperature
        use_tools = False
        last_error = ""

        # 2. First attempt + json_max_retries reask attempts.
        for _ in range(self._json_max_retries + 1):
            if last_error:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your previous response was invalid ({last_error}). "
                        f"Respond with ONLY a JSON object matching the schema."
                    ),
                })
            builder = (
                OpenAICompatJsonHelpers.build_tool_payload
                if use_tools
                else OpenAICompatJsonHelpers.build_json_schema_payload
            )
            payload = builder(self._model, messages, schema, tokens, temp)

            # 3. POST — a response_format rejection escalates once to the tool-calling fallback.
            try:
                response_json = await self._post_chat(payload)
            except httpx.HTTPStatusError as exc:
                if not use_tools and OpenAICompatJsonHelpers.is_response_format_unsupported(
                    exc.response.status_code, exc.response.text
                ):
                    self.logger.warning(f"generate_json: response_format unsupported — falling back to tool-calling.")
                    use_tools, last_error = True, ""
                    continue
                self.logger.warning(f"generate_json: HTTP error ({exc}) — returning empty dict.")
                return {}

            # 4. Extract → parse → validate; any failure feeds the reask loop.
            try:
                content = (
                    OpenAICompatJsonHelpers.extract_tool_args(response_json)
                    if use_tools
                    else OpenAICompatJsonHelpers.extract_content(response_json)
                )
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("response was not a JSON object")
                missing = OpenAICompatJsonHelpers.missing_required_keys(data, schema)
                if missing:
                    raise ValueError(f"missing required keys: {missing}")
                return data
            except (ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                self.logger.warning(f"generate_json: invalid response ({last_error}) — retrying.")

        # 5. Reask loop exhausted — degrade gracefully (the chunk keeps its existing metadata).
        self.logger.warning(f"generate_json: exhausted {self._json_max_retries} reask(s) — returning empty dict.")
        return {}

    async def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        POST a chat-completions request and return the parsed JSON response.

        Args:
            payload (dict): The request body.

        Returns:
            dict: The parsed OpenAI-compatible response.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()
