# ====== Code Summary ======
# Local OpenAI-compatible embedding provider — for self-hosted servers (vLLM, Ollama, LM Studio).
# No API key required. Dense-only (OpenAI protocol has no sparse endpoint).
# Config class lives in openai_compat_config.py (split to allow auto_import discovery).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from libs.providers.embed._openai_compat_base import _OpenAICompatBase


class LocalOpenAICompatEmbedProvider(_OpenAICompatBase):
    """
    Embedding provider for a locally-hosted OpenAI-compatible server.

    Designed for self-hosted inference servers that implement the OpenAI ``/embeddings``
    API without requiring authentication: vLLM, Ollama, LM Studio, FastEmbed-server, etc.

    No API key is required.  If your local server does require auth, pass ``api_key``
    explicitly; if it requires credentials you do not control, use ``OpenAIEmbedProvider``
    (``external/openai_compat.py``) instead.

    Config id: ``"openai_compat"``

    Attributes:
        name (str): ``"local-openai-compat"``
        version (str): ``"text-embedding-3-large"`` (default model name).
        runs_on (str): ``"local"``
    """

    name: str = "local-openai-compat"
    version: str = "text-embedding-3-large"
    runs_on: str = "local"

    def __init__(
        self,
        base_url: str,
        model: str = "",
        api_key: str = "",
        timeout_s: int = 30,
        batch_size: int = 32,
        dimension: int = 0,
    ) -> None:
        """
        Initialise the local OpenAI-compatible embedding provider.

        Args:
            base_url (str): Server URL (e.g. ``http://vllm:8000/v1``).
            model (str): Model name sent in the request body. Defaults to ``version``.
            api_key (str): Optional bearer token (empty = no ``Authorization`` header).
            timeout_s (int): HTTP timeout in seconds.  Default is 30 s (local network).
            batch_size (int): Maximum texts per batch request.
            dimension (int): Vector dimension override (0 = auto from known model names).
        """
        self._init_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model or self.version,
            timeout_s=timeout_s,
            batch_size=batch_size,
            dimension=dimension,
        )
        self.logger.debug(
            f"LocalOpenAICompatEmbedProvider: "
            f"model={self._model} dim={self._dimension} url={self._base_url}"
        )
