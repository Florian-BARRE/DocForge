# ====== Code Summary ======
# Pure-static helpers for HybridSearchService: vector-plan resolution,
# chunk-row → SearchResult mapping, query embedding + plan resolution,
# and Postgres-hydration of Qdrant hits.
#
# embed_and_resolve and hydrate are extracted from HybridSearchService._embed_and_resolve
# and HybridSearchService._hydrate to keep hybrid_search.py under 200 lines.
# They accept the service's dependencies as explicit arguments so they remain
# stateless pure functions with no I/O coupling.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from common_libs.search.field_index import CONTENT_DENSE, CONTENT_SPARSE, FieldIndexHelpers, RetrievalTuning
from .models import SearchResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from common_libs.providers.embed.base import EmbedProvider
    from common_libs.storage.postgres.repositories.chunk_repo import ChunkRepository


class HybridSearchHelpers:
    """
    Static helpers for HybridSearchService.

    All methods are pure functions (no I/O, no side-effects) and therefore
    carry no logger binding — the service handles all logging itself.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only class."""
        raise TypeError("HybridSearchHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve_vector_plan(
        metadata_fields: list[Any] | None,
        tuning: RetrievalTuning,
        weight_overrides: dict[str, float] | None,
    ) -> tuple[list[str], list[str], dict[str, float]]:
        """
        Build the searched named vectors and fusion weights from the schema + tuning.

        content_* vectors are always searched; each semantic metadata field adds a dense
        named vector, each lexical field a sparse one (spec §9).  Weights are layered:
        content weights and per-field weights come from ``tuning`` (the collection's
        search config), then ``weight_overrides`` (the request) win over everything.

        ``tuning.vector_mode`` restricts the plan: "dense" drops every sparse vector,
        "sparse" drops every dense vector, "hybrid" keeps both.

        Args:
            metadata_fields (list | None): Collection schema fields; ``None``/empty skips
                per-field vectors.
            tuning (RetrievalTuning): vector_mode, content weights, per-field weights.
            weight_overrides (dict[str, float] | None): Per-vector request overrides
                (highest priority).

        Returns:
            tuple[list[str], list[str], dict[str, float]]: A triple of
                ``(dense_vector_names, sparse_vector_names, weights)`` ready for
                ``QdrantStorageClient.multi_search``.
        """
        # 1. Derive named-vector plan from the collection's metadata schema
        plan = FieldIndexHelpers.derive_vector_plan(metadata_fields or [])

        # 2. Honor vector_mode — which families participate
        include_dense = tuning.vector_mode in ("hybrid", "dense")
        include_sparse = tuning.vector_mode in ("hybrid", "sparse")

        # 3. Build the vector lists: content always first within each enabled family
        dense_vectors = [CONTENT_DENSE, *plan.dense_vector_names] if include_dense else []
        sparse_vectors = [CONTENT_SPARSE, *plan.sparse_vector_names] if include_sparse else []

        # 4. Seed weights with content tuning, then per-field tuning (override schema 1.0)
        weights: dict[str, float] = {}
        if include_dense:
            weights[CONTENT_DENSE] = tuning.content_dense_weight
        if include_sparse:
            weights[CONTENT_SPARSE] = tuning.content_sparse_weight
        for fv in plan.dense:
            weights[fv.vector] = tuning.field_weights.get(fv.name, fv.weight)
        for fv in plan.sparse:
            weights[fv.vector] = tuning.field_weights.get(fv.name, fv.weight)

        # 5. Apply caller overrides (highest priority)
        if weight_overrides:
            weights.update(weight_overrides)

        return dense_vectors, sparse_vectors, weights

    @staticmethod
    def row_to_result(row: dict[str, Any], hit: dict[str, Any]) -> SearchResult:
        """
        Map a Postgres chunk row and its Qdrant hit to a ``SearchResult``.

        ``prov`` is read from the row when available (source of truth for provenance);
        the Qdrant payload is used as a fallback for ``pages`` only.

        Args:
            row (dict[str, Any]): Chunk row dict as returned by ``ChunkRepository``.
            hit (dict[str, Any]): Qdrant hit dict containing ``id``, ``score``, and
                ``payload`` keys.

        Returns:
            SearchResult: Fully populated result object.
        """
        # 1. Resolve page provenance: prefer the Postgres prov field, fall back to payload
        prov = row.get("prov")
        pages = prov.get("pages", []) if isinstance(prov, dict) else hit.get("payload", {}).get("pages", [])

        # 2. Build and return the result.
        #    chunk_id / document_id are UUIDs from Postgres — coerce to str so the
        #    API SearchResultItem (str fields) validates under Pydantic v2 strict typing.
        return SearchResult(
            chunk_id=str(row["id"]),
            document_id=str(row["document_id"]),
            score=hit["score"],
            raw_text=row["raw_text"],
            strategy=row["strategy"],
            token_count=row["token_count"],
            pages=pages,
            config_hash=row["config_hash"],
            block_ids=list(row["block_ids"]) if row["block_ids"] else [],
        )

    @staticmethod
    async def embed_and_resolve(
        embed_provider: EmbedProvider,
        query: str,
        metadata_fields: list[Any] | None,
        tuning: RetrievalTuning,
        weight_overrides: dict[str, float] | None,
    ) -> tuple[list[float], dict[int, float] | None, list[str], list[str], dict[str, float]]:
        """
        Embed the query and resolve the per-field vector plan and fusion weights.

        Shared front half of search and search_debug: one embed call yields the
        dense + sparse query vectors, then the collection schema + tuning are turned into
        the dense/sparse named-vector lists and their fusion weights.

        Args:
            embed_provider (EmbedProvider): The embed provider for query encoding.
            query (str): Natural language query string.
            metadata_fields (list | None): Collection's metadata schema for per-field vectors.
            tuning (RetrievalTuning): vector_mode + weights tuning.
            weight_overrides (dict[str, float] | None): Per-vector weight overrides.

        Returns:
            tuple: ``(dense_vec, sparse_vec, dense_vectors, sparse_vectors, weights)``.
        """
        # 1. Embed the query — produces dense + sparse in one HTTP round-trip
        embed_result = await embed_provider.embed([query])
        dense_vec = embed_result.vectors[0]
        sparse_vec = embed_result.sparse[0] if embed_result.sparse else None

        # 2. Resolve the multi-field vector plan + fusion weights from schema + tuning
        dense_vectors, sparse_vectors, weights = HybridSearchHelpers.resolve_vector_plan(
            metadata_fields, tuning, weight_overrides
        )
        return dense_vec, sparse_vec, dense_vectors, sparse_vectors, weights

    @staticmethod
    async def hydrate(
        session: AsyncSession,
        chunk_repo: ChunkRepository,
        logger: LoggerClass,
        raw_hits: list[dict[str, Any]],
    ) -> list[SearchResult]:
        """
        Fetch full chunk records from Postgres for the ranked hits (source of truth).

        Hierarchical mode: a hit child is rolled up to its section parent (the parent
        carries the full-section context), and multiple children of the same parent
        collapse to one result — the highest-ranked one wins.  Flat chunks are
        returned as-is.

        Args:
            session (AsyncSession): Active Postgres session.
            chunk_repo (ChunkRepository): Repository used to fetch chunk rows.
            logger (LoggerClass): The caller's logger for warning emission.
            raw_hits (list[dict]): Ranked hit dicts from Qdrant, each containing
                ``id``, ``score``, and ``payload`` keys.

        Returns:
            list[SearchResult]: Hydrated results in rank order; missing/duplicate rows skipped.
        """
        # 1. Batch-fetch the hit rows, then the parents they roll up to
        rows = await chunk_repo.get_by_ids(session, [hit["id"] for hit in raw_hits])
        parent_ids = [r["parent_id"] for r in rows.values() if r.get("parent_id")]
        parents = await chunk_repo.get_by_ids(session, parent_ids) if parent_ids else {}

        # 2. Walk hits in rank order, rolling children up to their parent and deduping
        results: list[SearchResult] = []
        seen: set[str] = set()
        for hit in raw_hits:
            row = rows.get(hit["id"])
            if row is None:
                # Qdrant has a point that Postgres lost — skip and warn
                logger.warning(
                    f"HybridSearch: chunk_id={hit['id']} found in Qdrant but missing from Postgres — skipping."
                )
                continue
            target = parents.get(row["parent_id"], row) if row.get("parent_id") else row
            if target["id"] in seen:
                continue
            seen.add(target["id"])
            results.append(HybridSearchHelpers.row_to_result(target, hit))
        return results
