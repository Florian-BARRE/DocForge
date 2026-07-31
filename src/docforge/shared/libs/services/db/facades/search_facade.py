# ====== Code Summary ======
# SearchFacade — the retrieval path: run the filtered hybrid search in Qdrant (fused with RRF over
# the named vectors) and return lean (chunk_id, score) pairs — the lean-vector principle. The
# unbypassable searchability exclusion (disabled chunks/documents) is injected here, so every caller
# (the graph read port) inherits it without re-deriving it. Postgres hydration is the caller's job.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import DocumentApi
from shared_libs.services.db.qdrant import (
    DOCUMENT_ID_KEY,
    ENABLED_KEY,
    Condition,
    Match,
    MatchAny,
    QdrantClient,
    QdrantSearchApi,
    SparseVec,
)

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


class SearchFacade(LoggerClass):
    """Filtered hybrid search (Qdrant) returning lean (chunk_id, score) pairs."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def hybrid_ids(
        self,
        collection_id: uuid.UUID,
        *,
        dense: dict[str, list[float]] | None = None,
        sparse: dict[str, SparseVec] | None = None,
        conditions: Sequence[Condition] = (),
        limit: int = 10,
        prefetch_limit: int | None = None,
        fusion: str = "rrf",
    ) -> list[tuple[str, float]]:
        """
        Run a collection's filtered hybrid search and return lean (chunk_id, score) pairs only.

        The vector side plus the unbypassable searchability exclusion — WITHOUT any Postgres
        hydration (that is the caller's job). The disabled-chunk / disabled-document exclusion
        invariant lives here, and here only, so every caller (the graph read port) inherits it
        without re-deriving it.

        Args:
            collection_id (uuid.UUID): The collection to search.
            dense (dict | None): vector name → query dense vector (content and/or meta fields).
            sparse (dict | None): vector name → query sparse vector.
            conditions (Sequence[Condition]): Filters on the filterable metadata fields.
            limit (int): Number of fused results.
            prefetch_limit (int | None): Per-branch candidate depth (defaults to an over-sample).
            fusion (str): Branch-fusion strategy — "rrf" (default) or "dbsf" (score-distribution
                fusion, lets a confident axis dominate).

        Returns:
            list[tuple[str, float]]: (chunk_id, fused score) pairs, best first (empty when the
                collection has no Qdrant space yet or nothing matched).
        """
        # 1. The vector side — fused (chunk_id, score) pairs.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        # A collection provisions its Qdrant space lazily at first indexing — searching one that was
        # created but never ingested has no space to query yet. Empty results, not a 500.
        if not await self._qdrant.raw.collection_exists(name):
            return []
        # 2. Enforce the searchability invariants, unbypassable from the router, via must_not only:
        #    drop a point when `enabled` is explicitly False (a disabled chunk, or a boilerplate role
        #    that defaults disabled) or when its document is disabled (bounded must_not over a cheap
        #    Postgres lookup — a doc toggle stays one PG flag, no Qdrant fan-out). Excluding on
        #    `enabled=False` (rather than requiring `enabled=True`) is migration-free and self-healing:
        #    a legacy point that predates the `enabled` payload write has no such flag, so it is not
        #    matched and stays searchable — treated as enabled by default, no Qdrant backfill needed.
        async with self._postgres.session() as session:
            disabled_doc_ids = await DocumentApi.list_disabled_ids(session, collection_id)
        exclusions: list[Condition] = [Match(field=ENABLED_KEY, value=False)]
        if disabled_doc_ids:
            exclusions.append(
                MatchAny(field=DOCUMENT_ID_KEY, values=[str(doc_id) for doc_id in disabled_doc_ids])
            )
        return await QdrantSearchApi.hybrid(
            self._qdrant.raw,
            name,
            dense=dense,
            sparse=sparse,
            conditions=conditions,
            exclusions=exclusions,
            limit=limit,
            prefetch_limit=prefetch_limit,
            fusion=fusion,
        )


__all__ = ["SearchFacade"]
