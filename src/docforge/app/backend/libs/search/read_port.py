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
from shared_libs.public_models.search import Candidate, EncodedQuery, Hit, SearchTarget
from shared_libs.services.db import Database
from shared_libs.services.db.qdrant import build_match_conditions

# ====== Local Project Imports ======
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

    async def hybrid_search(
        self,
        encoded: EncodedQuery,
        filters: dict,
        limit: int,
        targets: list[SearchTarget],
        fusion: str = "rrf",
    ) -> list[Candidate]:
        """
        Run the collection's filtered hybrid search and return candidates, best-first.

        The disabled-chunk / disabled-document exclusion is enforced inside SearchFacade.hybrid_ids,
        so it can never be bypassed here whatever the graph wiring. Retrieval stays lean here: the
        facade returns (chunk_id, score) pairs with NO Postgres hydration — the hydrate node fetches
        the rich fields for the cut top_k only, so the candidate pool is never hydrated twice.

        Args:
            encoded (EncodedQuery): The query's vectors (dense always; sparse when present).
            filters (dict): The structured filter map constraining the retrieval.
            limit (int): The candidate depth to return (the QuerySpec's ``candidate_k``).
            targets (list[SearchTarget]): The fields × modalities to search (content and/or metadata);
                resolved here to the named query-vector dicts (the only place that knows those names).
            fusion (str): Branch-fusion strategy — "rrf" (default) or "dbsf".

        Returns:
            list[Candidate]: Chunk ids + fused scores in retrieval order (empty when nothing matched).
        """
        # 1. Resolve the requested targets to the named query vectors (content and/or metadata) —
        #    the resolver is the ONE place that knows Qdrant vector names; the node never does. A
        #    targets set that resolves to no queryable vector (e.g. a lexical-only target whose
        #    collection embedder was later swapped to dense-only, past the router's validation)
        #    degrades to empty results rather than a 500.
        try:
            dense, sparse = TargetVectorResolver.resolve(encoded, targets)
        except ValueError as exc:
            self.logger.warning(f"Search targets resolved to no queryable vector: {exc}")
            return []

        # 2. Delegate to the LEAN facade retrieval — exclusion invariant lives inside it (reused,
        #    not re-derived), and it returns (chunk_id, score) pairs with NO Postgres hydration.
        scored = await self._database.search.hybrid_ids(
            self._collection_id,
            dense=dense,
            sparse=sparse,
            conditions=build_match_conditions(filters),
            limit=limit,
            fusion=fusion,
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

        # 3. Resolve source identity + declared metadata for the hit page's documents in TWO bulk
        #    reads (not per-hit) so every hit self-cites — the client never needs an N+1 GET
        #    /documents/{id} to render "which document, which fields".
        document_ids = list({row.document_id for row in rows})
        documents = {doc.id: doc for doc in await self._database.documents.get_by_ids(document_ids)}
        doc_metadata = await self._database.documents.get_filterable_metadata_for_documents(
            document_ids
        )

        # 4. Shape each row into a Hit; chunk_index/token_count + the source identity/metadata ride
        #    along in the metadata bag (lifted into the flat hit model by the router).
        hydrated = {}
        for row in rows:
            document = documents.get(row.document_id)
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
                },
            )
        self.logger.debug(f"Hydrated {len(hydrated)}/{len(chunk_ids)} chunk(s)")
        return hydrated


__all__ = ["CollectionReadPortImpl"]
