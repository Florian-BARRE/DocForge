# ====== Code Summary ======
# TEI embedding provider RUNTIME (L3 brick) — local Text Embeddings Inference / bge_server host.
# BGE-M3: dense 1024-dim + sparse BM25, via /embed and /embed_sparse endpoints. Consumed only at
# step level + by the chain assembler; built lazily by the embed CONFIG classes (which stay in the
# config layer). Implements the EmbedProvider contract (imported DOWNWARD from common_libs.providers).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
# Contracts stay in the (lower) provider/config layer; the runtime imports them DOWNWARD (no cycle).
from common_libs.providers.embed.base import EmbedProvider
from common_libs.providers.interfaces import EmbedResult


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
        runs_on (str): ``"local"`` or ``"remote"`` — set from the locality flag (a TEI server
            can be self-hosted or a remote endpoint, e.g. a hosted inference URL).
    """

    name: str = "tei-bge-m3"
    version: str = "BAAI/bge-m3"
    runs_on: str = "local"

    def __init__(
        self,
        base_url: str,
        model: str = "",
        locality: str = "local",
        api_key: str = "",
        timeout_s: int = 60,
        batch_size: int = 32,
        embed_sparse: bool = True,
    ) -> None:
        """
        Initialise the TEI embedding provider.

        Args:
            base_url (str): TEI server URL (e.g. ``http://bge_server:80``).
            model (str): Model identifier for cache keys. Defaults to ``version`` (BGE-M3).
            locality (str): "local" or "external" — sets runs_on for the device gate.
            api_key (str): Optional bearer token (sent as Authorization when non-empty; a
                remote TEI endpoint may require it, a local one usually does not).
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
        # Locality drives the device gate; auth header is added only when a key is supplied.
        self.runs_on = "remote" if locality == "external" else "local"
        self._headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.logger.debug(
            f"TeiEmbedProvider: locality={locality} model={self._model} url={self._base_url}"
        )

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
            response = await client.get(f"{self._base_url}/health", headers=self._headers)
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
                headers=self._headers,
            )
            dense_resp.raise_for_status()
            dense: list[list[float]] = dense_resp.json()

            # 2. Sparse BM25 — only when enabled
            sparse: list[dict[int, float]] | None = None
            if self._embed_sparse:
                sparse_resp = await client.post(
                    f"{self._base_url}/embed_sparse",
                    json={"inputs": texts, "truncate": True},
                    headers=self._headers,
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
