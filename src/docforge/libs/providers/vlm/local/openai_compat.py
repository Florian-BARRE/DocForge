# ====== Code Summary ======
# Local OpenAI-compatible VLM provider — for self-hosted servers (vLLM, Ollama, LM Studio).
# No API key required. Config id: "openai_compat"

from __future__ import annotations

# ====== Local Project Imports ======
from libs.capabilities.vlm._openai_compat_base import _OpenAICompatVlmBase


class LocalOpenAICompatVlmProvider(_OpenAICompatVlmBase):
    """
    VLM provider for locally-hosted OpenAI-compatible inference servers.

    Compatible with: vLLM, Ollama, LM Studio, OpenRouter (local), and any
    server implementing the OpenAI chat-completions vision API.

    No API key is required (empty default).  If your local server requires
    authentication, pass api_key explicitly.  For cloud APIs with mandatory
    auth, use OpenAIVlmProvider (external/openai_compat.py) instead.

    Config id: "openai_compat"

    Attributes:
        name (str): "local-openai-compat-vlm"
        version (str): Derived from the model name (last path segment).
        runs_on (str): "local"
    """

    name: str = "local-openai-compat-vlm"
    runs_on: str = "local"

    def __init__(
        self,
        api_base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: int = 30,
        max_tokens: int = 1024,
        cost_per_call: float = 0.0,
    ) -> None:
        """
        Initialize the local OpenAI-compatible VLM provider.

        Args:
            api_base_url (str): Server URL (e.g. http://vllm:8001/v1).
            model (str): Model identifier (e.g. Qwen/Qwen2.5-VL-7B-Instruct).
            api_key (str): Optional bearer token (empty = no Authorization header).
            timeout_s (int): HTTP timeout in seconds (default 30 s — local network).
            max_tokens (int): Max generated tokens per response.
            cost_per_call (float): Always 0.0 for local providers.
        """
        self._init_openai_compat_vlm(
            api_base_url=api_base_url,
            api_key=api_key,
            model=model,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            cost_per_call=cost_per_call,
        )
        self.logger.debug(
            f"LocalOpenAICompatVlmProvider: model={model!r} url={self._api_base_url}"
        )
