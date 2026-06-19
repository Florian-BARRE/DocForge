# ====== Code Summary ======
# TEI embedding provider — local Text Embeddings Inference server.
# BGE-M3: dense 1024-dim + sparse BM25, via /embed and /embed_sparse endpoints.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.embed.base import EmbedProvider
from libs.capabilities.interfaces import EmbedResult

# ====== Local Project Imports ======
# (none — TeiEmbedConfig lives in config.py to keep provider and config separate)


class TeiEmbedProvider(EmbedProvider, LoggerClass):
    """
    Embedding provider for a self-hosted TEI (Text Embeddings Inference) server.

    TEI protocol:
      - ``POST {base_url}/embed``          → dense vectors (normalized, float32)
      - ``POST {base_url}/embed_sparse``   → sparse BM25 token-weight maps
      - ``GET  {base_url}/health``         → liveness check

    Designed for BGE-M3 (1024-dim dense + BM25 sparse, enabling hybrid search).
    For cloud or OpenAI-compatible endpoints use the providers under ``external/``.

    Config id: ``"tei"``

    Attributes:
        name (str): ``"tei-bge-m3"``
        version (str): ``"BAAI/bge-m3"`` (default model name used in cache keys).
        runs_on (str): ``"local"`` — TEI is always a self-hosted service.
    """

    name: str = "tei-bge-m3"
    version: str = "BAAI/bge-m3"
    runs_on: str = "local"

    def __init__(
        self,
        base_url: str,
        model: str = "",
        timeout_s: int = 60,
        batch_size: int = 32,
        embed_sparse: bool = True,
    ) -> None:
        """
        Initialise the TEI embedding provider.

        Args:
            base_url (str): TEI server URL (e.g. ``http://tei:8080``).
            model (str): Model identifier for cache keys. Defaults to ``version`` (BGE-M3).
            timeout_s (int): HTTP timeout in seconds.
            batch_size (int): Maximum texts per batch request.
            embed_sparse (bool): When True, also request sparse (BM25) vectors.
        """
        LoggerClass.__init__(self)
        self._base_url = base_url.rstrip("/")
        self._model = model or self.version
        self._timeout_s = timeout_s
        self._batch_size = batch_size
        self._embed_sparse = embed_sparse
        self.logger.debug(f"TeiEmbedProvider: model={self._model} url={self._base_url}")

    @property
    def dimension(self) -> int:
        """Dense vector dimension — BGE-M3 always produces 1024-dim vectors.

        Returns:
            int: 1024
        """
        return 1024

    async def embed(self, texts: list[str]) -> EmbedResult:
        """
        Embed texts via the TEI server, producing dense and optional sparse vectors.

        Args:
            texts (list[str]): Input strings to embed.

        Returns:
            EmbedResult: Dense vectors + optional BM25 sparse maps.

        Raises:
            httpx.HTTPError: On network or server-side error.
        """
        if not texts:
            return EmbedResult(vectors=[], sparse=None, model=self._model)

        all_dense: list[list[float]] = []
        all_sparse: list[dict[int, float]] | None = [] if self._embed_sparse else None

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            dense, sparse = await self._embed_batch(batch)
            all_dense.extend(dense)
            if all_sparse is not None and sparse is not None:
                all_sparse.extend(sparse)

        return EmbedResult(
            vectors=all_dense,
            sparse=all_sparse if self._embed_sparse else None,
            model=self._model,
        )

    async def health_check(self, timeout_s: int = 5) -> None:
        """
        Verify the TEI server is alive via ``GET /health``.

        Args:
            timeout_s (int): Connection timeout in seconds.

        Raises:
            httpx.ConnectError: If the server is unreachable.
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(f"{self._base_url}/health")
            response.raise_for_status()
        self.logger.debug(f"TeiEmbedProvider: health check OK ({self._base_url}/health)")

    async def _embed_batch(
        self,
        texts: list[str],
    ) -> tuple[list[list[float]], list[dict[int, float]] | None]:
        """
        POST one batch to ``/embed`` and optionally ``/embed_sparse``.

        Args:
            texts (list[str]): Texts in this batch (length ≤ ``_batch_size``).

        Returns:
            tuple: ``(dense_vectors, sparse_dicts | None)``.

        Raises:
            httpx.HTTPError: On network or server-side error.
        """
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            # 1. Dense embeddings — always required
            dense_resp = await client.post(
                f"{self._base_url}/embed",
                json={"inputs": texts, "normalize": True, "truncate": True},
            )
            dense_resp.raise_for_status()
            dense: list[list[float]] = dense_resp.json()

            # 2. Sparse BM25 — only when enabled
            sparse: list[dict[int, float]] | None = None
            if self._embed_sparse:
                sparse_resp = await client.post(
                    f"{self._base_url}/embed_sparse",
                    json={"inputs": texts, "truncate": True},
                )
                sparse_resp.raise_for_status()
                # TEI returns: [[{"index": int, "value": float}, ...], ...]
                raw: list[list[dict[str, float]]] = sparse_resp.json()
                sparse = [
                    {int(t["index"]): float(t["value"]) for t in token_list}
                    for token_list in raw
                ]

        self.logger.debug(
            f"TeiEmbedProvider: {len(texts)} texts → "
            f"dense={len(dense)} sparse={'yes' if sparse else 'no'}"
        )
        return dense, sparse


# TeiEmbedConfig (the @register-decorated Pydantic config) lives in config.py
# to separate the provider implementation from its configuration / registry concerns.
