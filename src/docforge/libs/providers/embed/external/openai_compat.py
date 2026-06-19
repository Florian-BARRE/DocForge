# ====== Code Summary ======
# External OpenAI-compatible embedding provider — for cloud APIs (OpenAI, Azure, Mistral, …).
# API key is mandatory. Dense-only (OpenAI protocol has no sparse endpoint).
# Config class lives in openai_compat_config.py (split to allow auto_import discovery).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from libs.providers.embed._openai_compat_base import _OpenAICompatBase


class OpenAIEmbedProvider(_OpenAICompatBase):
    """
    Embedding provider for external OpenAI-compatible cloud APIs.

    Targets any cloud endpoint that implements the OpenAI ``/embeddings`` API and
    requires bearer token authentication: OpenAI, Azure OpenAI, Mistral, Cohere,
    Together AI, etc.

    An ``api_key`` is **required** — the constructor raises ``ValueError`` when it
    is empty so misconfiguration is caught at job start, not silently at inference time.

    Config id: ``"openai"``

    Attributes:
        name (str): ``"openai"``
        version (str): ``"text-embedding-3-large"`` (default model name).
        runs_on (str): ``"remote"``
    """

    name: str = "openai"
    version: str = "text-embedding-3-large"
    runs_on: str = "remote"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "",
        timeout_s: int = 60,
        batch_size: int = 32,
        dimension: int = 0,
    ) -> None:
        """
        Initialise the external OpenAI-compatible embedding provider.

        Args:
            base_url (str): API base URL (e.g. ``https://api.openai.com/v1``).
            api_key (str): Bearer token — **required**, raises if empty.
            model (str): Model name sent in the request body. Defaults to ``version``.
            timeout_s (int): HTTP timeout in seconds.  Default is 60 s (network latency).
            batch_size (int): Maximum texts per batch request.
            dimension (int): Vector dimension override (0 = auto from known model names).

        Raises:
            ValueError: When ``api_key`` is empty — external APIs always require auth.
        """
        if not api_key:
            raise ValueError(
                f"OpenAIEmbedProvider requires an api_key. "
                f"For local servers without auth, use LocalOpenAICompatEmbedProvider instead."
            )
        self._init_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model or self.version,
            timeout_s=timeout_s,
            batch_size=batch_size,
            dimension=dimension,
        )
        self.logger.debug(
            f"OpenAIEmbedProvider: "
            f"model={self._model} dim={self._dimension} url={self._base_url}"
        )
