# ====== Code Summary ======
# Shared OpenAI-compatible chat-completions HTTP logic for VLM providers.
# Implements describe() — subclasses only define the constructor contract.
# Stateless prompt builders and quality heuristic live in helpers.py.

# ====== Standard Library Imports ======
from __future__ import annotations

import base64
import json
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.interfaces import VlmResult
from libs.capabilities.vlm.base import VlmProvider

# ====== Local Project Imports ======
from .helpers import CHART_DATA_SCHEMA as _CHART_DATA_SCHEMA
from .helpers import OpenAICompatVlmHelpers


class _OpenAICompatVlmBase(VlmProvider, LoggerClass):
    """
    Shared HTTP implementation for all OpenAI-compatible VLM providers.

    Subclasses (LocalOpenAICompatVlmProvider, OpenAIVlmProvider) define their
    constructor contract (auth requirements, defaults) and delegate to
    _init_openai_compat_vlm().

    Protocol: POST {base_url}/chat/completions (vision variant, OpenAI shape).
    """

    CHART_DATA_SCHEMA: dict[str, Any] = _CHART_DATA_SCHEMA

    def _init_openai_compat_vlm(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        timeout_s: int,
        max_tokens: int,
        cost_per_call: float,
    ) -> None:
        """
        Initialize shared OpenAI-compat VLM state. Called from subclass __init__.

        Args:
            api_base_url (str): Base URL (e.g. http://vllm:8001/v1 or https://api.openai.com/v1).
            api_key (str): Bearer token (empty = no Authorization header).
            model (str): Model identifier sent in the request body.
            timeout_s (int): HTTP timeout in seconds.
            max_tokens (int): Max generated tokens per response.
            cost_per_call (float): Estimated USD per API call (0.0 for local).
        """
        LoggerClass.__init__(self)
        self._api_base_url = api_base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        self.cost_per_call: float = cost_per_call
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        # name / version from the model string
        self.name: str = self.__class__.name
        self.version: str = model.split("/")[-1]

    async def describe(
        self,
        img_bytes: bytes,
        grounding: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> VlmResult:
        """
        Generate a description (and optionally structured data) for an image.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            grounding (str | None): OCR text to ground the description (anti-hallucination).
            schema (dict | None): JSON schema for structured output (chart-to-data).

        Returns:
            VlmResult: Prose description + optional structured payload.

        Raises:
            httpx.HTTPError: On network or server-side error.
        """
        self.logger.debug(
            f"{self.name} describe: model={self._model!r} "
            f"grounded={grounding is not None} schema={schema is not None}"
        )

        # 1. Encode image as base64 data-URI
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"

        # 2. Build system + user messages
        system_prompt = OpenAICompatVlmHelpers.build_system_prompt(grounding, schema)
        user_content: list[dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
            {"type": "text", "text": OpenAICompatVlmHelpers.build_user_text(grounding, schema)},
        ]

        # 3. Build request payload
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": self._max_tokens,
            "temperature": 0.1,
        }

        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "figure_data", "schema": schema, "strict": True},
            }

        # 4. Call the API
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._api_base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()

        # 5. Parse response
        data = response.json()
        content: str = data["choices"][0]["message"]["content"]

        # 6. Extract description and structured payload
        structured: dict[str, Any] | None = None
        description: str = content

        if schema:
            try:
                structured = json.loads(content)
                description = structured.get("description", content)
            except json.JSONDecodeError:
                self.logger.warning(
                    f"{self.name}: structured output not valid JSON — using raw content "
                    f"(first 200 chars: {content[:200]!r})"
                )

        # 7. Adapter-side quality heuristic consumed by the VLM chain gate.
        #    1.0 — structured output was requested AND received non-empty
        #    0.5 — description-only path (or structured requested but invalid JSON)
        #    Note: providers that raise are scored 0 by the chain itself (succeeded=False).
        quality = OpenAICompatVlmHelpers.heuristic_quality(description, structured, schema is not None)

        self.logger.debug(
            f"{self.name} done: {len(description)} chars "
            f"structured={'yes' if structured else 'no'} quality={quality:.2f}"
        )
        return VlmResult(description=description, structured=structured, quality=quality)

    @staticmethod
    def chart_schema() -> dict[str, Any]:
        """
        Return the JSON schema for chart-to-data structured extraction.

        Returns:
            dict: JSON schema requiring 'description' (str) and 'table' (list[list[str]]).
        """
        return _CHART_DATA_SCHEMA
