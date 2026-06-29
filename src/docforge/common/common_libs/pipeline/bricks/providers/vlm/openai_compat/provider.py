# ====== Code Summary ======
# OpenAICompatVlmProvider — ONE OpenAI-compatible vision provider for both local and external
# servers. Locality is a runtime flag selecting runs_on (local/remote), the reported name, the
# default HTTP timeout, and the auth policy (api_key required iff external). Replaces the former
# LocalOpenAICompatVlmProvider + OpenAIVlmProvider, which differed only by those four points.

from __future__ import annotations

# ====== Local Project Imports ======
from common_libs.pipeline.bricks.providers.vlm._openai_compat_base import _OpenAICompatVlmBase

# Locality-dependent defaults: local networks are fast; cloud APIs need a longer ceiling.
_LOCAL_TIMEOUT_S = 30
_EXTERNAL_TIMEOUT_S = 120


class OpenAICompatVlmProvider(_OpenAICompatVlmBase):
    """
    VLM provider for any OpenAI chat-completions vision API, local or external.

    The ``locality`` flag selects the deployment:
      - ``"local"`` — vLLM / Ollama / LM Studio; api_key optional; runs_on="local".
      - ``"external"`` — OpenAI / Mistral / OpenRouter cloud; api_key REQUIRED; runs_on="remote".
    """

    # Class-level default; overridden per-instance from the locality flag (see __init__).
    name: str = "openai-compat-vlm"
    runs_on: str = "local"

    def __init__(
        self,
        api_base_url: str,
        model: str,
        locality: str = "local",
        api_key: str = "",
        timeout_s: int | None = None,
        max_tokens: int = 1024,
    ) -> None:
        """
        Initialize the unified OpenAI-compatible VLM provider.

        Args:
            api_base_url (str): Server URL (local vLLM or cloud endpoint).
            model (str): Model identifier sent in the request body.
            locality (str): "local" or "external" — sets runs_on, name, default timeout, auth policy.
            api_key (str): Bearer token. Required (non-empty) when locality == "external".
            timeout_s (int | None): HTTP timeout; defaults by locality when None (30 s local / 120 s cloud).
            max_tokens (int): Max generated tokens per response.

        Raises:
            ValueError: When locality == "external" and api_key is empty.
        """
        # 1. External cloud APIs must authenticate — fail at job start, not at inference time.
        if locality == "external" and not api_key:
            raise ValueError(
                "OpenAICompatVlmProvider: api_key is required when locality='external'. "
                "Use locality='local' for self-hosted servers without auth."
            )

        # 2. Resolve locality-dependent defaults before delegating to the shared base.
        resolved_timeout = timeout_s if timeout_s is not None else (
            _EXTERNAL_TIMEOUT_S if locality == "external" else _LOCAL_TIMEOUT_S
        )
        self._init_openai_compat_vlm(
            api_base_url=api_base_url,
            api_key=api_key,
            model=model,
            timeout_s=resolved_timeout,
            max_tokens=max_tokens,
        )

        # 3. Override identity from the locality flag (the base seeds name from the class attr).
        self.runs_on = "remote" if locality == "external" else "local"
        self.name = "openai-vlm" if locality == "external" else "local-openai-compat-vlm"
        self.logger.debug(
            f"OpenAICompatVlmProvider: locality={locality} model={model!r} url={self._api_base_url}"
        )
