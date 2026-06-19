# ====== Code Summary ======
# Pure helpers for the multi-field hybrid index (spec §7.2, §9): derive which named vectors
# a collection needs from its metadata schema, resolve a field's text value for a chunk, and
# combine per-vector ranked lists with weighted Reciprocal Rank Fusion. No I/O — fully unit
# testable and reused by S6 (indexing) and HybridSearchService (retrieval).

# ====== Standard Library Imports ======
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Canonical content vector names (always present), shared with the Qdrant client.
CONTENT_DENSE: str = "content_dense"
CONTENT_SPARSE: str = "content_bm25"

# RRF rank constant (standard k=60; larger → flatter rank influence).
RRF_K: int = 60


@dataclass(slots=True)
class FieldVec:
    """A metadata field promoted to a vector, with its fusion weight."""

    name: str          # original field name (e.g. "title")
    vector: str        # Qdrant named-vector key (e.g. "meta_title_dense")
    weight: float      # RRF fusion weight from the schema


@dataclass(slots=True)
class VectorPlan:
    """
    The named vectors a collection's metadata schema requires (beyond content).

    Attributes:
        dense (list[FieldVec]): One per ``semantic`` field — a dedicated named dense vector.
        sparse (list[FieldVec]): One per ``lexical`` field — a dedicated named sparse (BM25) vector.
    """

    dense: list[FieldVec] = field(default_factory=list)
    sparse: list[FieldVec] = field(default_factory=list)

    @property
    def dense_vector_names(self) -> list[str]:
        return [f.vector for f in self.dense]

    @property
    def sparse_vector_names(self) -> list[str]:
        return [f.vector for f in self.sparse]


class FieldIndexHelpers:
    """
    Static helpers for multi-field hybrid index operations (spec §7.2, §9).

    Covers: field-name sanitization, named-vector key derivation, vector plan computation,
    chunk-level text resolution, and weighted Reciprocal Rank Fusion.  All methods are pure
    functions with no I/O — fully unit-testable.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def _safe(name: str) -> str:
        """
        Sanitize a field name into a Qdrant-safe vector-name fragment.

        Args:
            name (str): Raw field name (may contain spaces, upper-case, or special chars).

        Returns:
            str: Lower-case alphanumeric slug with underscores; falls back to ``"field"``.
        """
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "field"

    @staticmethod
    def field_dense_name(field_name: str) -> str:
        """
        Named-vector key for a field's dense vector (namespaced to avoid content collision).

        Args:
            field_name (str): Metadata field name.

        Returns:
            str: Qdrant vector key in the form ``meta_<slug>_dense``.
        """
        return f"meta_{FieldIndexHelpers._safe(field_name)}_dense"

    @staticmethod
    def field_sparse_name(field_name: str) -> str:
        """
        Named-vector key for a field's sparse (BM25) vector.

        Args:
            field_name (str): Metadata field name.

        Returns:
            str: Qdrant vector key in the form ``meta_<slug>_bm25``.
        """
        return f"meta_{FieldIndexHelpers._safe(field_name)}_bm25"

    @staticmethod
    def derive_vector_plan(metadata_fields: list[Any]) -> VectorPlan:
        """
        Derive the per-field named vectors required by a collection's metadata schema.

        Args:
            metadata_fields (list): Field definitions — ORM rows or dicts carrying
                ``field_name``, ``semantic``, ``lexical``, ``weight_semantic``, ``weight_lexical``.

        Returns:
            VectorPlan: Dense vectors for semantic fields, sparse for lexical fields.
        """
        plan = VectorPlan()
        for f in metadata_fields:
            # 1. Read the field name; skip malformed entries
            name = FieldIndexHelpers._attr(f, "field_name")
            if not name:
                continue
            # 2. Semantic fields → named dense vector (equal weight — override at search time)
            if FieldIndexHelpers._attr(f, "semantic", False):
                plan.dense.append(FieldVec(
                    name=name,
                    vector=FieldIndexHelpers.field_dense_name(name),
                    weight=1.0,
                ))
            # 3. Lexical fields → named sparse (BM25) vector (equal weight — override at search time)
            if FieldIndexHelpers._attr(f, "lexical", False):
                plan.sparse.append(FieldVec(
                    name=name,
                    vector=FieldIndexHelpers.field_sparse_name(name),
                    weight=1.0,
                ))
        return plan

    @staticmethod
    def resolve_field_text(field_name: str, chunk: Any, doc_meta: dict[str, Any]) -> str | None:
        """
        Resolve the text value of a metadata field for a given chunk.

        Chunk-level fields come from the chunk's provenance; everything else (file-intrinsic,
        pipeline-derived doc stats, and custom business fields) comes from ``doc_meta`` — the
        merge of the document's implicit_meta + user_meta + a few derived values.

        Args:
            field_name (str): The metadata field name.
            chunk (Any): A Chunk (uses ``.prov``, ``.token_count``).
            doc_meta (dict): Document-level field values (implicit + user meta).

        Returns:
            str | None: The field's text value, or None when absent/empty (→ no vector emitted).
        """
        prov = getattr(chunk, "prov", {}) or {}
        # 1. Chunk-level fields — sourced from the chunk's own provenance
        if field_name == "heading_path":
            return (prov.get("heading_path") or "").strip() or None
        if field_name == "page":
            pages = prov.get("pages") or []
            return str(pages[0]) if pages else None
        if field_name == "block_type":
            bts = prov.get("block_types") or []
            return ",".join(bts) if bts else None
        if field_name == "token_count":
            return str(getattr(chunk, "token_count", "") or "") or None
        # 2. Document-level / custom fields — sourced from the merged document metadata
        value = doc_meta.get(field_name)
        if value is None or value == "":
            return None
        return str(value)

    @staticmethod
    def weighted_rrf(
        ranked_lists: dict[str, list[str]],
        weights: dict[str, float],
        top_k: int,
        rrf_k: int = RRF_K,
    ) -> list[tuple[str, float]]:
        """
        Combine per-vector ranked id lists into a single ranking via weighted RRF (spec §9).

        score(id) = Σ_vector  weight[vector] · 1 / (rrf_k + rank_vector(id))

        Args:
            ranked_lists (dict): vector_name → ordered list of chunk ids (best first).
            weights (dict): vector_name → fusion weight (missing → 1.0).
            top_k (int): Number of fused results to return.
            rrf_k (int): RRF rank constant.

        Returns:
            list[tuple[str, float]]: (chunk_id, fused_score) ordered by descending score.
        """
        scores: dict[str, float] = {}
        # 1. Accumulate weighted RRF contributions per vector
        for vector_name, ids in ranked_lists.items():
            w = weights.get(vector_name, 1.0)
            if w <= 0:
                continue
            for rank, cid in enumerate(ids):
                scores[cid] = scores.get(cid, 0.0) + w * (1.0 / (rrf_k + rank + 1))
        # 2. Sort by descending fused score and truncate to top_k
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ordered[:top_k]

    @staticmethod
    def _attr(obj: Any, name: str, default: Any = None) -> Any:
        """
        Read an attribute from either an ORM object or a dict.

        Args:
            obj (Any): ORM model instance or plain dict.
            name (str): Attribute / key name to look up.
            default (Any): Value to return when the attribute is absent.

        Returns:
            Any: The attribute value, or ``default`` if not found.
        """
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
