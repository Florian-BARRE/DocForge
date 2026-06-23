# ====== Code Summary ======
# CompositeEmbedProvider — pairs a dense embedding source with a SEPARATE sparse source.
# Dense vectors come from the dense provider; sparse (BM25) maps come from the sparse provider.
# This lets a dense-only backend (e.g. an external OpenAI-compatible API) be combined with a
# local sparse backend (e.g. a SPLADE TEI server) to enable hybrid search — the two embedding
# families legitimately live in different model spaces, one per named-vector family.
#
# Transparent to every consumer: it IS an EmbedProvider, so S6 indexing, the metadata indexer,
# and query-time search call ``.embed()`` unchanged and receive dense + sparse in one result.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.providers.embed.base import EmbedProvider
from libs.providers.results.embed_result import EmbedResult


class CompositeEmbedProvider(EmbedProvider, LoggerClass):
    """
    Embed provider that sources dense and sparse vectors from two distinct backends.

    Dense vectors (and the dimension / model identity) come from ``dense``; sparse maps come
    from ``sparse``. Both backends embed the same texts; the results are merged into a single
    EmbedResult so callers cannot tell the vectors came from different servers.

    Used when the dense backend cannot produce sparse vectors (e.g. OpenAI-compatible dense-only
    APIs, or TEI serving BGE-M3 with cls pooling) but the collection needs BM25/lexical vectors.
    """

    def __init__(self, dense: EmbedProvider, sparse: EmbedProvider) -> None:
        """
        Initialize the composite from a dense and a sparse provider.

        Args:
            dense (EmbedProvider): Source of dense vectors + dimension/model identity.
            sparse (EmbedProvider): Source of sparse (BM25) maps.
        """
        LoggerClass.__init__(self)
        self._dense = dense
        self._sparse = sparse
        # Surface the dense backend's identity (used in logs / cache keys / fingerprints).
        self.name = getattr(dense, "name", "composite")
        self.version = getattr(dense, "version", "")
        self.runs_on = getattr(dense, "runs_on", "local")
        self.logger.debug(
            f"CompositeEmbedProvider: dense={self.name} sparse={getattr(sparse, 'name', '?')}"
        )

    @property
    def dimension(self) -> int:
        """Dense vector dimension — taken from the dense backend (it defines the dense space)."""
        return self._dense.dimension

    async def embed(self, texts: list[str]) -> EmbedResult:
        """
        Embed texts, taking dense vectors from the dense backend and sparse maps from the sparse one.

        Args:
            texts (list[str]): Input strings to embed. May be empty.

        Returns:
            EmbedResult: Dense vectors from the dense backend, sparse maps from the sparse backend
                (aligned by input order). Sparse is None only when the sparse backend returns none.
        """
        # 1. Empty input — nothing to embed.
        if not texts:
            return EmbedResult(vectors=[], sparse=None, model=getattr(self._dense, "version", ""))

        # 2. Dense from the dense backend (authoritative for vectors + model identity).
        dense_res = await self._dense.embed(texts)

        # 3. Sparse from the dedicated sparse backend.
        sparse_res = await self._sparse.embed(texts)

        # 4. Merge — keep dense vectors/model, attach the sparse maps.
        return EmbedResult(
            vectors=dense_res.vectors,
            sparse=sparse_res.sparse,
            model=dense_res.model,
        )


# ------------------- Public API ------------------- #
__all__ = ["CompositeEmbedProvider"]
