# ====== Code Summary ======
# EmbedIndexIndexHelpers — the index-side static helpers for the embed_index stage. Pure mappings with
# no I/O: assemble the named dense/sparse vector maps Qdrant upsert expects (content + one per planned
# field), and build the lean Qdrant payload (base provenance + filterable field values) for a chunk.
# Used by the assemble_points node.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.metadata import MetadataHelpers
from common_libs.search.field_index import (
    CONTENT_DENSE,
    CONTENT_SPARSE,
    FieldIndexHelpers,
    VectorPlan,
)


class EmbedIndexIndexHelpers:
    """
    Pure-mapping static helpers for the embed_index stage's index phase.

    Assembles the named-vector maps for the Qdrant upsert and the per-chunk filterable payload.
    All methods are stateless pure mappings — no logging, no I/O.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("EmbedIndexIndexHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_vector_maps(
        plan: VectorPlan,
        content_dense: list[list[float] | None],
        content_sparse: list[dict[int, float] | None] | None,
        field_dense: dict[str, list[list[float] | None]],
        field_sparse: dict[str, list[dict[int, float] | None]],
    ) -> tuple[dict[str, list[list[float] | None]], dict[str, list[dict[int, float] | None]]]:
        """
        Assemble the named dense/sparse vector maps the Qdrant upsert consumes.

        The canonical ``content_dense`` vector is always present; ``content_bm25`` (sparse) is added
        only when the embed provider produced sparse vectors. Each planned semantic field contributes
        a named dense vector and each lexical field a named sparse vector, reusing the per-field
        vectors the embed phase produced.

        Args:
            plan (VectorPlan): The derived vector plan (named dense/sparse field vectors).
            content_dense (list): Per-chunk content dense vectors (aligned 1:1 with index_chunks).
            content_sparse (list | None): Per-chunk content sparse vectors, or None when none produced.
            field_dense (dict): Field name -> per-chunk dense vectors.
            field_sparse (dict): Field name -> per-chunk sparse vectors.

        Returns:
            tuple: ``(dense_by_vector, sparse_by_vector)`` keyed by Qdrant named-vector key.
        """
        # 1. Content body vectors — always materialised.
        dense_by_vector: dict[str, list[list[float] | None]] = {CONTENT_DENSE: content_dense}
        sparse_by_vector: dict[str, list[dict[int, float] | None]] = {}
        if content_sparse is not None:
            sparse_by_vector[CONTENT_SPARSE] = content_sparse

        # 2. One named vector per planned field (dense for semantic, sparse for lexical).
        for fv in plan.dense:
            dense_by_vector[fv.vector] = field_dense[fv.name]
        for fv in plan.sparse:
            sparse_by_vector[fv.vector] = field_sparse[fv.name]
        return dense_by_vector, sparse_by_vector

    @staticmethod
    def build_payload(
        chunk: Chunk,
        metadata_fields: list[Any],
        doc_meta: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the lean Qdrant payload: base provenance + filterable field values (spec 7.1).

        Only filterable fields are promoted to the payload — the rich content stays in Postgres.
        Hierarchical chunks carry a ``parent_id`` key so retrieval can roll a child up to its parent
        section.

        Args:
            chunk (Chunk): The chunk being indexed.
            metadata_fields (list[Any]): Collection metadata field definitions (3-flags + weights).
            doc_meta (dict[str, Any]): Document-level field values (implicit + user meta).

        Returns:
            dict[str, Any]: The Qdrant payload dict for this chunk.
        """
        # 1. Base provenance — always present on every Qdrant point.
        payload: dict[str, Any] = {
            "document_id": chunk.document_id,
            "config_hash": chunk.config_hash,
            "strategy": chunk.strategy,
            "token_count": chunk.token_count,
            "pages": chunk.prov.get("pages", []),
        }

        # 2. Hierarchical mode: carry the parent id so retrieval can roll a child up to its section.
        if chunk.parent_id:
            payload["parent_id"] = chunk.parent_id

        # 3. Promote filterable metadata field values into the payload.
        for f in metadata_fields:
            if MetadataHelpers.field_attr(f, "filterable", False):
                name = MetadataHelpers.field_attr(f, "field_name")
                value = FieldIndexHelpers.resolve_field_text(name, chunk, doc_meta)
                if value is not None:
                    payload[name] = value
        return payload


__all__ = ["EmbedIndexIndexHelpers"]
