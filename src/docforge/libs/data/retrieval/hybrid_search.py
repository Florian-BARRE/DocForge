# ====== Code Summary ======
# HybridSearchService: orchestrates query embedding → Qdrant hybrid RRF search →
# Postgres chunk fetch.  Returns fully materialized SearchResult objects ready for
# the API response.  Qdrant is the routing index; Postgres is the source of truth.
#
# Pure-static helpers (vector-plan resolution, row→result mapping, embed+resolve,
# hydration) live in hybrid_search_helpers.HybridSearchHelpers.
# The SearchResult dataclass lives in hybrid_search_models.SearchResult.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.capabilities.embed.local.tei import TeiEmbedProvider
from libs.data.storage.postgres.repositories.chunk_repo import ChunkRepository
from libs.data.storage.qdrant.client import QdrantStorageClient

# ====== Local Project Imports ======
from .hybrid_search_helpers import HybridSearchHelpers
from .hybrid_search_models import SearchResult


class HybridSearchService(LoggerClass):
    """
    Orchestrates hybrid retrieval for a single collection.

    Workflow:
    1. Embed the query text using TeiEmbedProvider (dense + sparse in one call).
    2. Call QdrantStorageClient.search() — server-side RRF fusion.
    3. Fetch full chunk records from Postgres for the top-k IDs.
    4. Return hydrated SearchResult objects.

    The class is stateless beyond its injected dependencies and can be shared
    across requests.  Pure-static helpers are delegated to HybridSearchHelpers.
    """

    def __init__(
        self,
        embed_provider: TeiEmbedProvider,
        qdrant: QdrantStorageClient,
        chunk_repo: ChunkRepository,
    ) -> None:
        """
        Initialize the hybrid search service.

        Args:
            embed_provider (TeiEmbedProvider): Embedding provider for query encoding.
            qdrant (QdrantStorageClient): Qdrant client for vector retrieval.
            chunk_repo (ChunkRepository): Postgres repository for chunk hydration.
        """
        LoggerClass.__init__(self)
        self._embed = embed_provider
        self._qdrant = qdrant
        self._chunk_repo = chunk_repo

    async def search(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        session: AsyncSession,
        payload_filter: dict | None = None,
        metadata_fields: list[Any] | None = None,
        weight_overrides: dict[str, float] | None = None,
    ) -> list[SearchResult]:
        """
        Execute a hybrid search and return hydrated results.

        Args:
            collection_name (str): Qdrant collection name (== Postgres collection id string).
            query (str): Natural language query string.
            top_k (int): Maximum number of results to return.
            session (AsyncSession): Active Postgres session for chunk hydration.
            payload_filter (dict | None): Optional Qdrant payload filter dict.
            metadata_fields (list | None): Collection's metadata schema for per-field vectors.
            weight_overrides (dict[str, float] | None): Per-vector weight overrides.

        Returns:
            list[SearchResult]: Results ordered by descending RRF score.

        Raises:
            RuntimeError: If Qdrant client is not connected.
            httpx.HTTPError: If the TEI server is unreachable.
        """
        # 1. Embed the query + resolve the multi-field vector plan and fusion weights
        dense_vec, sparse_vec, dense_vectors, sparse_vectors, weights = (
            await HybridSearchHelpers.embed_and_resolve(
                self._embed, query, metadata_fields, weight_overrides
            )
        )
        self.logger.debug(
            f"HybridSearch: query={query[:60]!r}… "
            f"dense_vecs={len(dense_vectors)} sparse_vecs={len(sparse_vectors)} top_k={top_k}"
        )

        # 2. Weighted multi-vector RRF retrieval
        raw_hits = await self._qdrant.multi_search(
            collection_name=collection_name,
            dense_query=dense_vec,
            sparse_query=sparse_vec,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            weights=weights,
            top_k=top_k,
            payload_filter=payload_filter,
        )
        if not raw_hits:
            return []

        # 3. Hydrate full chunk records from Postgres (source of truth)
        results = await HybridSearchHelpers.hydrate(
            session, self._chunk_repo, self.logger, raw_hits
        )
        self.logger.info(
            f"HybridSearch: collection={collection_name!r} hits={len(results)}/{top_k} query={query[:40]!r}…"
        )
        return results

    async def search_debug(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        session: AsyncSession,
        payload_filter: dict | None = None,
        metadata_fields: list[Any] | None = None,
        weight_overrides: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Run a search exposing the fusion internals (per-vector ranked lists + fused order).

        Args:
            collection_name (str): Qdrant collection name (== Postgres collection id string).
            query (str): Natural language query string.
            top_k (int): Maximum number of results to return.
            session (AsyncSession): Active Postgres session for chunk hydration.
            payload_filter (dict | None): Optional Qdrant payload filter dict.
            metadata_fields (list | None): Collection's metadata schema for per-field vectors.
            weight_overrides (dict[str, float] | None): Per-vector weight overrides.

        Returns:
            dict: ``{resolved, ranked, fused, results}`` — ``results`` are hydrated
                SearchResult objects; ``ranked``/``fused`` explain how each chunk was ranked.
        """
        # 1. Embed + resolve the plan (same as search)
        dense_vec, sparse_vec, dense_vectors, sparse_vectors, weights = (
            await HybridSearchHelpers.embed_and_resolve(
                self._embed, query, metadata_fields, weight_overrides
            )
        )

        # 2. Debug retrieval — keep the per-vector ranked lists + fused scores
        debug = await self._qdrant.multi_search_debug(
            collection_name=collection_name, dense_query=dense_vec, sparse_query=sparse_vec,
            dense_vectors=dense_vectors, sparse_vectors=sparse_vectors, weights=weights,
            top_k=top_k, payload_filter=payload_filter,
        )

        # 3. Hydrate the winners from Postgres
        results = await HybridSearchHelpers.hydrate(
            session, self._chunk_repo, self.logger, debug["results"]
        )
        return {
            "resolved": {
                "dense_vectors": dense_vectors, "sparse_vectors": sparse_vectors, "weights": weights,
                "candidate_limit": debug["candidate_limit"], "sparse_enabled": sparse_vec is not None,
            },
            "ranked": debug["ranked"],
            "fused": debug["fused"],
            "results": results,
        }
