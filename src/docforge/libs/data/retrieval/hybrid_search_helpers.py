# ====== Code Summary ======
# Pure-static helpers for HybridSearchService: vector-plan resolution and
# chunk-row → SearchResult mapping.  No async, no I/O, no logger binding
# (all methods are pure functions; a logger would be unused here).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Local Project Imports ======
from .field_index import CONTENT_DENSE, CONTENT_SPARSE, FieldIndexHelpers
from .hybrid_search_models import SearchResult


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
        weight_overrides: dict[str, float] | None,
    ) -> tuple[list[str], list[str], dict[str, float]]:
        """
        Build the searched named vectors and fusion weights from the collection schema.

        content_* vectors are always searched (weight 1.0); each semantic metadata
        field adds a dense named vector, each lexical field a sparse one, each with
        its schema weight (spec §9).  weight_overrides win over schema weights.

        Args:
            metadata_fields (list | None): Collection schema fields; ``None`` or empty
                list skips per-field vectors.
            weight_overrides (dict[str, float] | None): Caller-supplied weight
                overrides (highest priority).

        Returns:
            tuple[list[str], list[str], dict[str, float]]: A triple of
                ``(dense_vector_names, sparse_vector_names, weights)`` ready for
                ``QdrantStorageClient.multi_search``.
        """
        # 1. Derive named-vector plan from the collection's metadata schema
        plan = FieldIndexHelpers.derive_vector_plan(metadata_fields or [])

        # 2. Build the list of vectors to query: content always included first
        dense_vectors = [CONTENT_DENSE, *plan.dense_vector_names]
        sparse_vectors = [CONTENT_SPARSE, *plan.sparse_vector_names]

        # 3. Seed weights with content defaults, then layer in schema field weights
        weights: dict[str, float] = {CONTENT_DENSE: 1.0, CONTENT_SPARSE: 1.0}
        for fv in plan.dense:
            weights[fv.vector] = fv.weight
        for fv in plan.sparse:
            weights[fv.vector] = fv.weight

        # 4. Apply caller overrides (highest priority)
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

        # 2. Build and return the result
        return SearchResult(
            chunk_id=row["id"],
            document_id=str(row["document_id"]),
            score=hit["score"],
            raw_text=row["raw_text"],
            strategy=row["strategy"],
            token_count=row["token_count"],
            pages=pages,
            config_hash=row["config_hash"],
            block_ids=list(row["block_ids"]) if row["block_ids"] else [],
        )
