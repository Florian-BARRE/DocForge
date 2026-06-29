# ====== Code Summary ======
# Pure helpers for the multi-field hybrid index (spec §7.2, §9): derive which named vectors
# a collection needs from its metadata schema, resolve a field's text value for a chunk, and
# combine per-vector ranked lists with weighted Reciprocal Rank Fusion. No I/O — fully unit
# testable and reused by S6 (indexing) and HybridSearchService (retrieval).

# ====== Standard Library Imports ======
from __future__ import annotations

import re
import statistics
from typing import Any

# ====== Local Project Imports ======
from .models import RRF_K, FieldVec, VectorPlan


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

        Resolution order: chunk provenance (hardcoded chunk-level keys) → chunk ``derived_meta``
        (S5b chunk-scope generated fields) → ``doc_meta`` (file-intrinsic, pipeline-derived doc
        stats, document-scope generated values, and custom business fields). The merged ``doc_meta``
        is the document's implicit_meta + user_meta + document-scope generated values + derived stats.

        Args:
            field_name (str): The metadata field name.
            chunk (Any): A Chunk (uses ``.prov``, ``.token_count``, ``.derived_meta``).
            doc_meta (dict): Document-level field values (implicit + user + document-scope generated).

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
        # 2. Chunk-scope generated fields (S5b) — sourced from the chunk's own derived_meta, ahead of
        #    the document-scope fallback so a per-chunk value wins over any broadcast doc-level value.
        derived = getattr(chunk, "derived_meta", {}) or {}
        if field_name in derived:
            return FieldIndexHelpers._stringify(derived.get(field_name))
        # 3. Document-level / custom fields — sourced from the merged document metadata
        return FieldIndexHelpers._stringify(doc_meta.get(field_name))

    @staticmethod
    def _stringify(value: Any) -> str | None:
        """
        Coerce a resolved field value into index text, or None when empty.

        A list (e.g. a ``keyword_list`` / ``string[]`` generated field) is comma-joined; ``None``
        and the empty string collapse to None so no vector / payload entry is emitted.

        Args:
            value (Any): The raw resolved value (scalar, list, or None).

        Returns:
            str | None: The text representation, or None when absent/empty.
        """
        if value is None or value == "":
            return None
        if isinstance(value, list):
            joined = ",".join(str(v) for v in value if v is not None and v != "")
            return joined or None
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
    def dbsf_fuse(
        scored_lists: dict[str, list[tuple[str, float]]],
        weights: dict[str, float],
        top_k: int,
    ) -> list[tuple[str, float]]:
        """
        Combine per-vector scored lists with Distribution-Based Score Fusion (DBSF).

        Each vector's raw similarity scores are normalized to [0, 1] using 3-sigma
        bounds (``mean ± 3·std``) so heterogeneous score scales (cosine vs. BM25) become
        comparable, then summed with per-vector weights.  This is Qdrant's DBSF strategy
        reproduced client-side so it composes with the multi-field weighted plan.

        Args:
            scored_lists (dict): vector_name → ordered list of ``(chunk_id, raw_score)``.
            weights (dict): vector_name → fusion weight (missing → 1.0).
            top_k (int): Number of fused results to return.

        Returns:
            list[tuple[str, float]]: ``(chunk_id, fused_score)`` ordered by descending score.
        """
        totals: dict[str, float] = {}
        # 1. Per vector: normalize scores via 3-sigma bounds, accumulate weighted sum
        for vector_name, items in scored_lists.items():
            w = weights.get(vector_name, 1.0)
            if w <= 0 or not items:
                continue
            raw = [s for _, s in items]
            if len(raw) == 1:
                lo, hi = raw[0], raw[0]
            else:
                mean = statistics.fmean(raw)
                std = statistics.pstdev(raw)
                lo, hi = mean - 3.0 * std, mean + 3.0 * std
            span = hi - lo
            for cid, score in items:
                norm = 0.0 if span <= 0 else (score - lo) / span
                norm = min(1.0, max(0.0, norm))
                totals[cid] = totals.get(cid, 0.0) + w * norm
        # 2. Sort by descending fused score and truncate to top_k
        ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
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
