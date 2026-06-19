# ====== Code Summary ======
# External OpenAI-compatible VLM provider — for cloud APIs (OpenAI, Mistral, OpenRouter).
# API key is mandatory. Config id: "openai"

from __future__ import annotations

# ====== Local Project Imports ======
from libs.capabilities.vlm._openai_compat_base import _OpenAICompatVlmBase


class OpenAIVlmProvider(_OpenAICompatVlmBase):
    """
    VLM provider for external OpenAI-compatible cloud APIs.

    Compatible with: OpenAI (GPT-4o, GPT-4-vision), Mistral vision,
    Gemini-compat endpoints, OpenRouter, and any cloud API that implements
    the OpenAI chat-completions shape with vision support.

    An api_key is REQUIRED — the constructor raises ValueError when empty
    so misconfiguration is caught at job start, not silently at inference time.

    Config id: "openai"

    Attributes:
        name (str): "openai-vlm"
        version (str): Derived from the model name (last path segment).
        runs_on (str): "remote"
    """

    name: str = "openai-vlm"
    runs_on: str = "remote"

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 120,
        max_tokens: int = 1024,
        cost_per_call: float = 0.0,
    ) -> None:
        """
        Initialize the external OpenAI-compatible VLM provider.

        Args:
            api_base_url (str): Cloud API base URL (e.g. https://api.openai.com/v1).
            api_key (str): Bearer token — REQUIRED, raises ValueError if empty.
            model (str): Model identifier (e.g. gpt-4o, mistral-vision-latest).
            timeout_s (int): HTTP timeout in seconds (default 120 s — cloud latency).
            max_tokens (int): Max generated tokens per response.
            cost_per_call (float): Estimated USD per call for budget tracking.

        Raises:
            ValueError: When api_key is empty — cloud APIs always require auth.
        """
        if not api_key:
            raise ValueError(
                "OpenAIVlmProvider requires an api_key. "
                "For local servers without auth, use LocalOpenAICompatVlmProvider instead."
            )
        self._init_openai_compat_vlm(
            api_base_url=api_base_url,
            api_key=api_key,
            model=model,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            cost_per_call=cost_per_call,
        )
        self.logger.debug(
            f"OpenAIVlmProvider: model={model!r} url={self._api_base_url}"
        )
