# ====== Code Summary ======
# OpenAI-compatible embedding provider — ONE class for both local and external servers.
# Locality is a runtime flag, not a separate class: "external" (cloud APIs: OpenAI/Azure/
# Mistral — api_key required) and "local" (self-hosted: vLLM/Ollama/LM Studio — api_key
# optional) share the exact same OpenAI /embeddings protocol. Dense-only.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from libs.providers.embed._openai_compat_base import _OpenAICompatBase


class OpenAICompatEmbedProvider(_OpenAICompatBase):
    """
    Embedding provider for any OpenAI ``/embeddings`` server, local or external.

    The ``locality`` flag distinguishes the two deployments that previously had separate
    classes:
      - ``"external"`` — cloud APIs (OpenAI, Azure, Mistral, Cohere…); ``api_key`` is required.
      - ``"local"``    — self-hosted (vLLM, Ollama, LM Studio, FastEmbed…); ``api_key`` optional.

    It sets ``runs_on`` from ``locality`` so the locality gate resolves correctly. Dense-only
    (the OpenAI protocol has no sparse endpoint — pair with a sparse source for hybrid).

    Config id: ``"openai_compat"``
    """

    name: str = "openai-compat"
    version: str = "text-embedding-3-large"
    runs_on: str = "local"

    def __init__(
        self,
        base_url: str,
        locality: str = "local",
        api_key: str = "",
        model: str = "",
        timeout_s: int = 0,
        batch_size: int = 32,
        dimension: int = 0,
    ) -> None:
        """
        Initialise the OpenAI-compatible embedding provider.

        Args:
            base_url (str): Server URL (e.g. ``https://api.openai.com/v1`` or ``http://vllm:8000/v1``).
            locality (str): ``"local"`` or ``"external"`` — sets ``runs_on`` and the auth policy.
            api_key (str): Bearer token. Required when ``locality == "external"``.
            model (str): Model name sent in the request body. Defaults to ``version``.
            timeout_s (int): HTTP timeout; defaults to 60 s (external) / 30 s (local) when 0.
            batch_size (int): Maximum texts per batch request.
            dimension (int): Vector dimension override (0 = auto from known model names).

        Raises:
            ValueError: When ``locality == "external"`` and ``api_key`` is empty.
        """
        # External cloud APIs always require auth — fail fast at job start, not at inference.
        if locality == "external" and not api_key:
            raise ValueError(
                "OpenAICompatEmbedProvider: api_key is required when locality='external'."
            )
        self.runs_on = "remote" if locality == "external" else "local"
        self._locality = locality
        self._init_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model or self.version,
            timeout_s=timeout_s or (60 if locality == "external" else 30),
            batch_size=batch_size,
            dimension=dimension,
        )
        self.logger.debug(
            f"OpenAICompatEmbedProvider: locality={locality} model={self._model} "
            f"dim={self._dimension} url={self._base_url}"
        )
