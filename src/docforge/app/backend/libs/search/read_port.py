# ====== Code Summary ======
# CollectionReadPortImpl — the concrete, read-only CollectionReadPort a search graph reaches through
# the engine's bind() seam. It is the ONLY component in the search request path that touches the raw
# data facades: a retrieve/hydrate node never imports a store. hybrid_search delegates to the LEAN
# SearchFacade.hybrid_ids, which bakes in the disabled-chunk / disabled-document exclusion
# (search_facade.py) and returns (chunk_id, score) pairs WITHOUT hydration — so the unbypassable
# exclusion comes for free, no composed graph can fetch a disabled point, and the DELIVERED pool is
# hydrated once (by the hydrate node, on the cut top_k). A rerank node, when present, additionally
# reads ONLY the passage text of its top_n through this same port to score them — a separate scoped
# read, not a re-hydration of the delivered pool. hydrate delegates to the documents facade's bulk
# chunk read. Constructed per-request, scoped to one collection; carries no cross-request state.

# ====== Standard Library Imports ======
import asyncio
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.search import CollectionReadPort
from shared_libs.public_models.search import Candidate, EncodedQuery, Hit, SearchTarget
from shared_libs.services.db import Database
from shared_libs.services.db.qdrant import build_match_conditions

# ====== Local Project Imports ======
from .probe import (
    AXES_DENSE_ONLY,
    AXES_DENSE_SPARSE,
    AXES_NONE,
    AXES_SPARSE_ONLY,
    SearchRetrievalProbe,
)
from .target_resolver import TargetVectorResolver

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
        # Per-request retrieval probe — the app-side accumulator the SearchMetricsEmitter reads at
        # the runner boundary. The port is constructed per request (SearchService), so this rides
        # along with per-request scope; it is NOT part of the shared CollectionReadPort protocol (an
        # observability attribute would leak an app concern into the engine-side contract), so the
        # runner reads it defensively via getattr.
        self.probe = SearchRetrievalProbe()

    async def hybrid_search(
        self,
        encoded: EncodedQuery,
        filters: dict,
        limit: int,
        targets: list[SearchTarget],
        fusion: str = "rrf",
        measure_branch_contribution: bool = False,
    ) -> list[Candidate]:
        """
        Run the collection's filtered hybrid search and return candidates, best-first.

        The disabled-chunk / disabled-document exclusion is enforced inside SearchFacade.hybrid_ids,
        so it can never be bypassed here whatever the graph wiring. Retrieval stays lean here: the
        facade returns (chunk_id, score) pairs with NO Postgres hydration — the hydrate node fetches
        the rich fields for the cut top_k only, so the DELIVERED pool is hydrated once (a rerank
        node, when present, separately reads only its top_n passage text to score them).

        Args:
            encoded (EncodedQuery): The query's vectors (dense always; sparse when present).
            filters (dict): The structured filter map constraining the retrieval.
            limit (int): The candidate depth to return (the QuerySpec's ``candidate_k``).
            targets (list[SearchTarget]): The fields × modalities to search (content and/or metadata);
                resolved here to the named query-vector dicts (the only place that knows those names).
            fusion (str): Branch-fusion strategy — "rrf" (default) or "dbsf".
            measure_branch_contribution (bool): When True, run two extra concurrent probe queries
                (dense-only / sparse-only) AFTER the authoritative hybrid call so the emitter can
                report each branch's share of the fused pool. Best-effort (a probe failure never
                fails the search) and OFF by default — the default path issues EXACTLY one query.

        Returns:
            list[Candidate]: Chunk ids + fused scores in retrieval order (empty when nothing matched).
        """
        # 1. Resolve the requested targets to the named query vectors (content and/or metadata) —
        #    the resolver is the ONE place that knows Qdrant vector names; the node never does. A
        #    targets set that resolves to no queryable vector (e.g. a lexical-only target whose
        #    collection embedder was later swapped to dense-only, past the router's validation)
        #    degrades to empty results rather than a 500 — and is counted as a filter-only call, not
        #    silently lost (the "axes=none" reading of "filter-only vs vector").
        try:
            dense, sparse = TargetVectorResolver.resolve(encoded, targets)
        except ValueError as exc:
            self.logger.warning(f"Search targets resolved to no queryable vector: {exc}")
            self.probe.record_call(AXES_NONE, bool(filters), [])
            return []

        # 2. Delegate to the LEAN facade retrieval — exclusion invariant lives inside it (reused,
        #    not re-derived), and it returns (chunk_id, score) pairs with NO Postgres hydration.
        conditions = build_match_conditions(filters)
        scored = await self._database.search.hybrid_ids(
            self._collection_id,
            dense=dense,
            sparse=sparse,
            conditions=conditions,
            limit=limit,
            fusion=fusion,
            max_disabled_exclusions=RUNTIME_CONFIG.SEARCH_MAX_DISABLED_DOC_EXCLUSIONS,
        )

        # 3. Build lean candidates straight from the pairs — the DELIVERED pool is hydrated once, by
        #    the hydrate node on the cut top_k (a rerank node, if wired, separately reads only its
        #    top_n passage text to score them). Provenance is the retrieval branch.
        candidates = [
            Candidate(chunk_id=chunk_id, score=score, source=_RETRIEVAL_SOURCE)
            for chunk_id, score in scored
        ]
        # 4. Record this call's shape facts on the per-request probe (no metric import here).
        self.probe.record_call(
            self.__classify_axes(dense, sparse),
            bool(filters),
            [candidate.chunk_id for candidate in candidates],
        )

        # 5. Opt-in branch breakdown — only when BOTH axes were queried (a single-axis retrieval has a
        #    trivial 100% breakdown). Best-effort: a probe failure leaves the breakdown unrecorded but
        #    NEVER touches the authoritative candidates already in hand.
        if measure_branch_contribution and dense and sparse:
            await self.__probe_branches(dense, sparse, conditions, limit, fusion)

        self.logger.debug(
            f"Hybrid search on {self._collection_id} returned {len(candidates)} candidate(s)"
        )
        return candidates

    @staticmethod
    def __classify_axes(dense: dict, sparse: dict | None) -> str:
        """Classify a retrieval call by which axes it queried (bounded probe enum)."""
        # 1. Both, dense-only or sparse-only — the resolver never returns neither (it raises).
        if dense and sparse:
            return AXES_DENSE_SPARSE
        if dense:
            return AXES_DENSE_ONLY
        return AXES_SPARSE_ONLY

    async def __probe_branches(
        self,
        dense: dict,
        sparse: dict,
        conditions: list,
        limit: int,
        fusion: str,
    ) -> None:
        """
        Run the two concurrent dense-only / sparse-only probe queries and record their id sets.

        Same conditions/limit as the authoritative call so the pools are comparable; issued together
        via asyncio.gather so the added wall-clock is +1 round-trip (not +2). Best-effort: any probe
        failure is caught, counted, and leaves the breakdown unrecorded — the search is unaffected.

        Args:
            dense (dict): The dense named-vector map (queried alone in the dense-only probe).
            sparse (dict): The sparse named-vector map (queried alone in the sparse-only probe).
            conditions (list): The same match conditions the authoritative call used.
            limit (int): The same candidate depth the authoritative call used.
            fusion (str): The same fusion strategy (irrelevant single-branch, kept for parity).
        """
        # 1. Fire both single-branch queries concurrently, capturing exceptions instead of raising.
        try:
            dense_scored, sparse_scored = await asyncio.gather(
                self._database.search.hybrid_ids(
                    self._collection_id,
                    dense=dense,
                    sparse=None,
                    conditions=conditions,
                    limit=limit,
                    fusion=fusion,
                    max_disabled_exclusions=RUNTIME_CONFIG.SEARCH_MAX_DISABLED_DOC_EXCLUSIONS,
                ),
                self._database.search.hybrid_ids(
                    self._collection_id,
                    dense=None,
                    sparse=sparse,
                    conditions=conditions,
                    limit=limit,
                    fusion=fusion,
                    max_disabled_exclusions=RUNTIME_CONFIG.SEARCH_MAX_DISABLED_DOC_EXCLUSIONS,
                ),
            )
        except Exception as exc:
            self.probe.record_branch_error()
            self.logger.warning(f"Dense/sparse branch probe failed (breakdown skipped): {exc}")
            return

        # 2. Record the per-branch id sets on the probe — the emitter derives the fused-pool shares.
        self.probe.record_branches(
            {chunk_id for chunk_id, _ in dense_scored},
            {chunk_id for chunk_id, _ in sparse_scored},
        )

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

        # 3. Resolve source identity + declared metadata for the hit page's documents in TWO bulk
        #    reads (not per-hit) so every hit self-cites — the client never needs an N+1 GET
        #    /documents/{id} to render "which document, which fields".
        document_ids = list({row.document_id for row in rows})
        documents = {doc.id: doc for doc in await self._database.documents.get_by_ids(document_ids)}
        doc_metadata = await self._database.documents.get_filterable_metadata_for_documents(
            document_ids
        )

        # 4. Bulk-read each chunk's source blocks (page + bbox) so a hit self-cites WHERE on the page
        #    it came from — one query for the whole hit page (no per-hit N+1), the primary block is
        #    the first in assembly order.
        block_locations = await self._database.documents.get_block_locations_for_chunks(
            [row.id for row in rows]
        )

        # 5. Shape each row into a Hit; chunk_index/token_count + the source identity/metadata + the
        #    block location ride along in the metadata bag (lifted into the flat hit model by the router).
        hydrated = {}
        for row in rows:
            document = documents.get(row.document_id)
            locations = block_locations.get(str(row.id), [])
            primary = locations[0] if locations else None
            hydrated[str(row.id)] = Hit(
                chunk_id=str(row.id),
                document_id=str(row.document_id),
                text=row.text,
                metadata={
                    "chunk_index": row.chunk_index,
                    "token_count": row.token_count,
                    "heading_path": row.heading_path or [],
                    "filename": document.filename if document else None,
                    "document_title": (document.title or None) if document else None,
                    "document_metadata": doc_metadata.get(row.document_id, {}),
                    "block_ids": [loc["block_id"] for loc in locations],
                    "page": primary["page"] if primary else None,
                    "bbox": primary["bbox"] if primary else None,
                    "block_locations": [
                        {"page": loc["page"], "bbox": loc["bbox"]} for loc in locations
                    ],
                },
            )
        self.logger.debug(f"Hydrated {len(hydrated)}/{len(chunk_ids)} chunk(s)")
        return hydrated


__all__ = ["CollectionReadPortImpl"]
