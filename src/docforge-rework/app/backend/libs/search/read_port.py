# ====== Code Summary ======
# CollectionReadPortImpl — the concrete, read-only CollectionReadPort a search graph reaches through
# the engine's bind() seam. It is the ONLY component in the search request path that touches the raw
# data facades: a retrieve/hydrate node never imports a store. hybrid_search delegates to the LEAN
# SearchFacade.hybrid_ids, which bakes in the disabled-chunk / disabled-document exclusion
# (search_facade.py) and returns (chunk_id, score) pairs WITHOUT hydration — so the unbypassable
# exclusion comes for free, no composed graph can fetch a disabled point, and the candidate pool is
# hydrated exactly once (by the hydrate node, on the cut top_k). hydrate delegates to the documents
# facade's bulk chunk read. Constructed
# per-request, scoped to one collection; carries no cross-request state.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.search import CollectionReadPort
from shared_libs.public_models.search import Candidate, EncodedQuery, Hit
from shared_libs.services.db import Database
from shared_libs.services.db.qdrant import Condition, Match, MatchAny, SparseVec, VectorNames

# The default fused-pool depth a late-interaction re-score works over when the caller sets none —
# the same default the live search facade uses (search_facade.py:48).
_DEFAULT_RESCORE_POOL_SIZE = 100
# The retrieval branch that produced a candidate (provenance recorded on every Candidate).
_RETRIEVAL_SOURCE = "hybrid"


class CollectionReadPortImpl(CollectionReadPort, LoggerClass):
    """Read-only retrieval over SearchFacade (exclusion baked in) + the documents chunk read."""

    def __init__(self, database: Database, collection_id: uuid.UUID) -> None:
        """
        Args:
            database (Database): The shared data facade (its search + documents facades are used).
            collection_id (uuid.UUID): The collection every read is scoped to.
        """
        LoggerClass.__init__(self)
        self._database = database
        self._collection_id = collection_id

    def __conditions(self, filters: dict) -> list[Condition]:
        """
        Translate a ``{field: value}`` filter map into typed Qdrant conditions.

        A scalar becomes an equality match; a list becomes a set-membership (any-of) match. Field
        filterability is the query-intake node's concern (deferred), so the port trusts the filters
        it is handed and does not drop unknown fields here.

        Args:
            filters (dict): The structured filter map carried on the QuerySpec.

        Returns:
            list[Condition]: The ANDed conditions.
        """
        # 1. One condition per requested field — list → any-of, scalar → exact.
        conditions: list[Condition] = []
        for name, value in (filters or {}).items():
            if isinstance(value, list):
                conditions.append(MatchAny(field=name, values=value))
            else:
                conditions.append(Match(field=name, value=value))
        return conditions

    async def hybrid_search(
        self,
        encoded: EncodedQuery,
        filters: dict,
        limit: int,
        rescore_pool_size: int | None = None,
    ) -> list[Candidate]:
        """
        Run the collection's filtered hybrid search and return candidates, best-first.

        The disabled-chunk / disabled-document exclusion is enforced inside SearchFacade.hybrid_ids,
        so it can never be bypassed here whatever the graph wiring. Retrieval stays lean here: the
        facade returns (chunk_id, score) pairs with NO Postgres hydration — the hydrate node fetches
        the rich fields for the cut top_k only, so the candidate pool is never hydrated twice.

        Args:
            encoded (EncodedQuery): The query's vectors (dense always; sparse/colbert when present).
            filters (dict): The structured filter map constraining the retrieval.
            limit (int): The candidate depth to return (the QuerySpec's ``candidate_k``).
            rescore_pool_size (int | None): Late-interaction re-score pool size; None uses the
                store default.

        Returns:
            list[Candidate]: Chunk ids + fused scores in retrieval order (empty when nothing matched).
        """
        # 1. Name the query vectors with the SAME constants the persistence side writes.
        dense = {VectorNames.CONTENT_DENSE: encoded.dense}
        sparse = (
            {VectorNames.CONTENT_SPARSE: SparseVec(
                indices=encoded.sparse.indices, values=encoded.sparse.values
            )}
            if encoded.sparse is not None
            else None
        )

        # 2. Delegate to the LEAN facade retrieval — exclusion invariant lives inside it (reused,
        #    not re-derived), and it returns (chunk_id, score) pairs with NO Postgres hydration.
        scored = await self._database.search.hybrid_ids(
            self._collection_id,
            dense=dense,
            sparse=sparse,
            conditions=self.__conditions(filters),
            limit=limit,
            colbert=encoded.colbert,
            rescore_pool_size=rescore_pool_size or _DEFAULT_RESCORE_POOL_SIZE,
        )

        # 3. Build lean candidates straight from the pairs — the pool is hydrated exactly once, by
        #    the hydrate node on the cut top_k. Provenance is the retrieval branch.
        candidates = [
            Candidate(chunk_id=chunk_id, score=score, source=_RETRIEVAL_SOURCE)
            for chunk_id, score in scored
        ]
        self.logger.debug(
            f"Hybrid search on {self._collection_id} returned {len(candidates)} candidate(s)"
        )
        return candidates

    async def hydrate(self, chunk_ids: list[str]) -> dict[str, Hit]:
        """
        Fetch the rich fields (document_id, text, metadata) for each chunk id — read-only Postgres.

        Args:
            chunk_ids (list[str]): The candidate chunk ids to hydrate.

        Returns:
            dict[str, Hit]: chunk_id → Hit carrying document_id/text/metadata (score/rank left at
                their defaults; the hydrate node assigns the authoritative rank/score). An id with
                no row is absent from the map (deleted between search and hydration).
        """
        # 1. Nothing to hydrate — short-circuit before a pointless round-trip.
        if not chunk_ids:
            return {}

        # 2. Bulk-read the chunk rows through the documents facade (the explorer's chunk read).
        rows = await self._database.documents.get_chunks_by_ids(
            [uuid.UUID(chunk_id) for chunk_id in chunk_ids]
        )

        # 3. Shape each row into a Hit; chunk_index/token_count ride along in metadata (nothing
        #    the live SearchResponse exposes is lost).
        hydrated = {
            str(row.id): Hit(
                chunk_id=str(row.id),
                document_id=str(row.document_id),
                text=row.text,
                metadata={"chunk_index": row.chunk_index, "token_count": row.token_count},
            )
            for row in rows
        }
        self.logger.debug(f"Hydrated {len(hydrated)}/{len(chunk_ids)} chunk(s)")
        return hydrated


__all__ = ["CollectionReadPortImpl"]
