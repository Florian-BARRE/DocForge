# ====== Code Summary ======
# HybridSearchService: orchestrates query embedding → Qdrant hybrid RRF search →
# Postgres chunk fetch.  Returns fully materialized SearchResult objects ready for
# the API response.  Qdrant is the routing index; Postgres is the source of truth.
#
# Pure-static helpers (vector-plan resolution, row→result mapping) live in
# hybrid_search_helpers.HybridSearchHelpers.
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
        # 1. Embed the query — produces dense + sparse in one HTTP round-trip
        embed_result = await self._embed.embed([query])
        dense_vec = embed_result.vectors[0]
        sparse_vec = embed_result.sparse[0] if embed_result.sparse else None

        # 2. Resolve the multi-field vector plan + fusion weights from the schema
        dense_vectors, sparse_vectors, weights = HybridSearchHelpers.resolve_vector_plan(
            metadata_fields, weight_overrides
        )
        self.logger.debug(
            f"HybridSearch: query={query[:60]!r}… "
            f"dense_vecs={len(dense_vectors)} sparse_vecs={len(sparse_vectors)} top_k={top_k}"
        )

        # 3. Weighted multi-vector RRF retrieval
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

        # 4. Hydrate full chunk records from Postgres (source of truth)
        results = await self._hydrate(session, raw_hits)
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
        embed_result = await self._embed.embed([query])
        dense_vec = embed_result.vectors[0]
        sparse_vec = embed_result.sparse[0] if embed_result.sparse else None
        dense_vectors, sparse_vectors, weights = HybridSearchHelpers.resolve_vector_plan(
            metadata_fields, weight_overrides
        )

        # 2. Debug retrieval — keep the per-vector ranked lists + fused scores
        debug = await self._qdrant.multi_search_debug(
            collection_name=collection_name, dense_query=dense_vec, sparse_query=sparse_vec,
            dense_vectors=dense_vectors, sparse_vectors=sparse_vectors, weights=weights,
            top_k=top_k, payload_filter=payload_filter,
        )

        # 3. Hydrate the winners from Postgres
        results = await self._hydrate(session, debug["results"])
        return {
            "resolved": {
                "dense_vectors": dense_vectors, "sparse_vectors": sparse_vectors, "weights": weights,
                "candidate_limit": debug["candidate_limit"], "sparse_enabled": sparse_vec is not None,
            },
            "ranked": debug["ranked"],
            "fused": debug["fused"],
            "results": results,
        }

    # ─── Internal ─────────────────────────────────────────────────────────────

    async def _hydrate(
        self, session: AsyncSession, raw_hits: list[dict[str, Any]]
    ) -> list[SearchResult]:
        """
        Fetch full chunk records from Postgres for the ranked hits (source of truth).

        Hierarchical mode: a hit child is rolled up to its section parent (the parent carries the
        full-section context), and multiple children of the same parent collapse to one result —
        the highest-ranked one wins.  Flat chunks are returned as-is.

        Args:
            session (AsyncSession): Active Postgres session.
            raw_hits (list[dict]): Ranked hit dicts from Qdrant, each containing
                ``id``, ``score``, and ``payload`` keys.

        Returns:
            list[SearchResult]: Hydrated results in rank order; missing/duplicate rows skipped.
        """
        # 1. Batch-fetch the hit rows, then the parents they roll up to
        rows = await self._chunk_repo.get_by_ids(session, [hit["id"] for hit in raw_hits])
        parent_ids = [r["parent_id"] for r in rows.values() if r.get("parent_id")]
        parents = await self._chunk_repo.get_by_ids(session, parent_ids) if parent_ids else {}

        # 2. Walk hits in rank order, rolling children up to their parent and deduping
        results: list[SearchResult] = []
        seen: set[str] = set()
        for hit in raw_hits:
            row = rows.get(hit["id"])
            if row is None:
                # Qdrant has a point that Postgres lost — skip and warn
                self.logger.warning(
                    f"HybridSearch: chunk_id={hit['id']} found in Qdrant but missing from Postgres — skipping."
                )
                continue
            target = parents.get(row["parent_id"], row) if row.get("parent_id") else row
            if target["id"] in seen:
                continue
            seen.add(target["id"])
            results.append(HybridSearchHelpers.row_to_result(target, hit))
        return results
