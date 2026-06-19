# ====== Code Summary ======
# Private base class for OpenAI-compatible embedding providers.
# Implements the shared /embeddings HTTP call so that local and external variants
# only need to define their constructor contract (auth requirements, defaults).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.embed.base import EmbedProvider
from libs.capabilities.interfaces import EmbedResult

# Known dense dimensions for well-known OpenAI model names.
# Used to pre-configure the Qdrant collection with the correct vector size.
_KNOWN_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


class _OpenAICompatBase(EmbedProvider, LoggerClass):
    """
    Shared HTTP implementation for any OpenAI-compatible ``/embeddings`` endpoint.

    Subclasses (``LocalOpenAICompatEmbedProvider``, ``OpenAIEmbedProvider``) define
    their own constructor with the appropriate defaults and validation, then delegate
    to ``_init_openai_compat``.

    This class is private to the ``embed`` package — import the concrete subclasses.

    Protocol:
        POST ``{base_url}/embeddings``
        Body: ``{"model": "<model>", "input": ["text1", "text2", ...]}``
        Auth: ``Authorization: Bearer {api_key}`` (omitted when ``api_key`` is empty)
        Response: ``{"data": [{"embedding": [float, ...]}, ...]}``

    Dense-only — the OpenAI protocol has no sparse endpoint.
    Use ``TeiEmbedProvider`` when hybrid dense+sparse is required.
    """

    KNOWN_DIMENSIONS: dict[str, int] = _KNOWN_DIMENSIONS

    def _init_openai_compat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: int,
        batch_size: int,
        dimension: int,
    ) -> None:
        """
        Initialise shared OpenAI-compat state.  Called from subclass ``__init__``.

        Args:
            base_url (str): API base URL (e.g. ``https://api.openai.com/v1``).
            api_key (str): Bearer token.  Empty = no ``Authorization`` header.
            model (str): Model identifier sent in the request body.
            timeout_s (int): HTTP timeout in seconds.
            batch_size (int): Maximum texts per batch request.
            dimension (int): Vector dimension override (0 = auto from ``KNOWN_DIMENSIONS``).
        """
        LoggerClass.__init__(self)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._batch_size = batch_size
        self._dimension = dimension or _KNOWN_DIMENSIONS.get(model, 1536)

    @property
    def dimension(self) -> int:
        """Dense vector dimension for the configured model.

        Returns:
            int: Dense vector dimension.
        """
        return self._dimension

    async def embed(self, texts: list[str]) -> EmbedResult:
        """
        Embed texts via ``POST /embeddings``, batching automatically.

        Args:
            texts (list[str]): Input strings.

        Returns:
            EmbedResult: Dense vectors only (``sparse=None``).

        Raises:
            httpx.HTTPError: On network or server-side error.
        """
        if not texts:
            return EmbedResult(vectors=[], sparse=None, model=self._model)

        all_dense: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            all_dense.extend(await self._embed_batch(batch))

        return EmbedResult(vectors=all_dense, sparse=None, model=self._model)

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        POST one batch to ``/embeddings`` and return the dense vectors.

        Args:
            texts (list[str]): Texts in this batch (length ≤ ``_batch_size``).

        Returns:
            list[list[float]]: One dense vector per input text.

        Raises:
            httpx.HTTPError: On network or server-side error.
        """
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": texts},
                headers=headers,
            )
            response.raise_for_status()

        dense: list[list[float]] = [item["embedding"] for item in response.json()["data"]]
        self.logger.debug(f"{self.name}: {len(texts)} texts → dim={len(dense[0]) if dense else 0}")
        return dense
