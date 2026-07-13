# ====== Code Summary ======
# SearchFacade — the retrieval path: run the filtered hybrid search in Qdrant (fused with RRF over
# the named vectors), then hydrate the winning chunk ids from Postgres — the lean-vector principle
# end to end. Returns SearchHits in fusion order; a point whose chunk row has vanished (deleted
# between search and hydration) is skipped with a warning rather than crashing the request.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, DocumentApi
from shared_libs.services.db.qdrant import (
    Condition,
    Match,
    MatchAny,
    QdrantClient,
    QdrantSearchApi,
    SparseVec,
)

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .payloads import SearchHit


class SearchFacade(LoggerClass):
    """Hybrid filtered search (Qdrant) + hydration (Postgres)."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def hybrid(
        self,
        collection_id: uuid.UUID,
        *,
        dense: dict[str, list[float]] | None = None,
        sparse: dict[str, SparseVec] | None = None,
        conditions: Sequence[Condition] = (),
        limit: int = 10,
        prefetch_limit: int | None = None,
        colbert: list[list[float]] | None = None,
        rescore_pool_size: int = 100,
    ) -> list[SearchHit]:
        """
        Search a collection and return hydrated hits, best first.

        Args:
            collection_id (uuid.UUID): The collection to search.
            dense (dict | None): vector name → query dense vector (content and/or meta fields).
            sparse (dict | None): vector name → query sparse vector.
            conditions (Sequence[Condition]): Filters on the filterable metadata fields.
            limit (int): Number of fused results.
            prefetch_limit (int | None): Per-branch candidate depth (defaults to an over-sample).
            colbert (list[list[float]] | None): The query's ColBERT multi-vector; when given, the
                search becomes a late-interaction re-score over the fused pool (MAX_SIM).
            rescore_pool_size (int): Size of the fused pool the ColBERT stage re-scores.

        Returns:
            list[SearchHit]: Hydrated chunks with their scores, best first.
        """
        # 1. The vector side — fused (chunk_id, score) pairs.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        # A collection provisions its Qdrant space lazily at first indexing — searching one that was
        # created but never ingested has no space to query yet. Empty results, not a 500.
        if not await self._qdrant.raw.collection_exists(name):
            return []
        # 2. Enforce the searchability invariants, unbypassable from the router: exclude the points
        #    of disabled chunks (the `enabled` payload flag) and of disabled documents (a bounded
        #    must_not over a cheap Postgres lookup — a doc toggle stays one PG flag, no Qdrant fan-out).
        search_conditions = [*conditions, Match(field="enabled", value=True)]
        async with self._postgres.session() as session:
            disabled_doc_ids = await DocumentApi.list_disabled_ids(session, collection_id)
        exclusions = (
            [MatchAny(field="document_id", values=[str(doc_id) for doc_id in disabled_doc_ids])]
            if disabled_doc_ids
            else []
        )
        scored = await QdrantSearchApi.hybrid(
            self._qdrant.raw,
            name,
            dense=dense,
            sparse=sparse,
            conditions=search_conditions,
            exclusions=exclusions,
            limit=limit,
            prefetch_limit=prefetch_limit,
            colbert=colbert,
            rescore_pool_size=rescore_pool_size,
        )
        if not scored:
            return []
        # 3. Hydrate the rich side from Postgres, preserving the fusion order.
        async with self._postgres.session() as session:
            chunks = await ChunkApi.get_by_ids(
                session, [uuid.UUID(chunk_id) for chunk_id, _ in scored]
            )
        by_id = {chunk.id: chunk for chunk in chunks}
        hits: list[SearchHit] = []
        for chunk_id, score in scored:
            chunk = by_id.get(uuid.UUID(chunk_id))
            if chunk is None:
                # Deleted between search and hydration — skip rather than fail the request.
                self.logger.warning(f"Search hit {chunk_id} has no chunk row; skipping")
                continue
            hits.append(SearchHit(chunk=chunk, score=score))
        return hits


__all__ = ["SearchFacade"]
