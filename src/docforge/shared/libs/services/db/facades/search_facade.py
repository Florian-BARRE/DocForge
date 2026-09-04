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
from sqlalchemy.ext.asyncio import AsyncSession

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
        max_disabled_exclusions: int | None = None,
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
            max_disabled_exclusions (int | None): Cap on the disabled-document must_not list (None =
                unbounded, the legacy behaviour). Past the cap the document filter FLIPS to a positive
                enabled-inclusion (the smaller set) so a mostly-archived collection never rides a huge
                must_not on EVERY query.

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
        # 2. Enforce the searchability invariants, unbypassable from the router. The disabled-CHUNK
        #    guard is always a must_not on `enabled == False` (migration-free + self-healing: a legacy
        #    point predating the flag is not matched, so it stays searchable). The disabled-DOCUMENT
        #    guard is bounded (see __apply_document_scope) so it can never bloat every query on a big
        #    archived collection.
        exclusions: list[Condition] = [Match(field=ENABLED_KEY, value=False)]
        conditions = list(conditions)
        async with self._postgres.session() as session:
            await self.__apply_document_scope(
                session, collection_id, conditions, exclusions, max_disabled_exclusions
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

    async def __apply_document_scope(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        conditions: list[Condition],
        exclusions: list[Condition],
        cap: int | None,
    ) -> None:
        """
        Wire the document-level searchability filter — a bounded must_not, or a positive fallback.

        Under the cap (or when uncapped): a ``must_not document_id in {disabled}`` exclusion (a doc
        toggle stays one PG flag, no Qdrant fan-out). Over the cap: that must_not would bloat EVERY
        query, so it FLIPS to a ``must document_id in {enabled}`` positive inclusion — correct and
        equivalent, but sized by the (smaller) enabled set on a mostly-archived collection.

        Args:
            session (AsyncSession): The open read session.
            collection_id (uuid.UUID): The collection being searched.
            conditions (list[Condition]): The must list (a positive inclusion is appended here).
            exclusions (list[Condition]): The must_not list (a bounded exclusion is appended here).
            cap (int | None): The disabled-exclusion cap (None = unbounded, legacy behaviour).
        """
        # 1. Uncapped (legacy) — the whole disabled set as a must_not (or nothing when none disabled).
        if cap is None:
            disabled = await DocumentApi.list_disabled_ids(session, collection_id)
            if disabled:
                exclusions.append(
                    MatchAny(field=DOCUMENT_ID_KEY, values=[str(d) for d in disabled])
                )
            return

        # 2. Capped — read one past the cap so an over-cap set is detected without loading it whole.
        disabled = await DocumentApi.list_disabled_ids(session, collection_id, limit=cap + 1)
        if len(disabled) <= cap:
            if disabled:
                exclusions.append(
                    MatchAny(field=DOCUMENT_ID_KEY, values=[str(d) for d in disabled])
                )
            return

        # 3. Fallback — too many disabled docs; flip to a positive enabled-inclusion (must) so the
        #    per-query filter is sized by the enabled set, not the huge disabled one.
        enabled = await DocumentApi.list_enabled_ids(session, collection_id)
        conditions.append(MatchAny(field=DOCUMENT_ID_KEY, values=[str(d) for d in enabled]))
        self.logger.warning(
            f"Collection {collection_id}: disabled-document exclusion exceeded its cap ({cap}) — "
            f"search switched to a positive enabled-inclusion of {len(enabled)} document(s)"
        )


__all__ = ["SearchFacade"]
