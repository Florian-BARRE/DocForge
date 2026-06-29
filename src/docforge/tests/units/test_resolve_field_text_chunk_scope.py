# ====== Code Summary ======
# Unit tests for FieldIndexHelpers.resolve_field_text — the three-level resolution order.
# The key invariant added by S5b: chunk.derived_meta (chunk-scope generated fields) is
# consulted BEFORE doc_meta so a per-chunk value wins over any broadcast doc-level value.

import uuid
from typing import Any

import pytest

from common_libs.domain.ir.chunk import Chunk
from common_libs.search.field_index.helpers import FieldIndexHelpers


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _chunk(
    raw_text: str = "chunk text",
    prov: dict | None = None,
    derived_meta: dict | None = None,
) -> Chunk:
    """Build a minimal Chunk with optional prov + derived_meta override."""
    c = Chunk(
        id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        config_hash="cfg",
        block_ids=["b1"],
        raw_text=raw_text,
        embed_text="",
        token_count=5,
        strategy="recursive_structure_aware",
    )
    if prov is not None:
        c.prov.update(prov)
    if derived_meta is not None:
        c.derived_meta.update(derived_meta)
    return c


# ─── Chunk-scope generated fields (derived_meta) ──────────────────────────────

class TestDerivedMetaPriority:
    """chunk.derived_meta is read BEFORE doc_meta (the chunk-scope priority rule)."""

    def test_derived_meta_wins_over_doc_meta(self) -> None:
        """A value in derived_meta shadows the same key in doc_meta."""
        chunk = _chunk(derived_meta={"kw": "chunk-value"})
        doc_meta: dict[str, Any] = {"kw": "doc-value"}
        result = FieldIndexHelpers.resolve_field_text("kw", chunk, doc_meta)
        assert result == "chunk-value"

    def test_derived_meta_absent_falls_through_to_doc_meta(self) -> None:
        """When a field is not in derived_meta it falls through to doc_meta."""
        chunk = _chunk(derived_meta={})
        doc_meta: dict[str, Any] = {"kw": "doc-only"}
        result = FieldIndexHelpers.resolve_field_text("kw", chunk, doc_meta)
        assert result == "doc-only"

    def test_derived_meta_none_value_falls_through_to_doc_meta(self) -> None:
        """A None value in derived_meta is NOT stored by the stage (stage skips None);
        this test confirms the resolver treats a missing key as a clean fallback."""
        chunk = _chunk(derived_meta={})
        doc_meta: dict[str, Any] = {"summary": "document summary"}
        result = FieldIndexHelpers.resolve_field_text("summary", chunk, doc_meta)
        assert result == "document summary"

    def test_derived_meta_empty_string_returns_none(self) -> None:
        """An empty string in derived_meta collapses to None (no vector emitted)."""
        chunk = _chunk(derived_meta={"kw": ""})
        result = FieldIndexHelpers.resolve_field_text("kw", chunk, {"kw": "doc-value"})
        # The stage should not write empty strings; but if it does, the resolver collapses them.
        assert result is None

    def test_derived_meta_list_comma_joined(self) -> None:
        """A list value (keyword_list) in derived_meta is comma-joined for the index."""
        chunk = _chunk(derived_meta={"tags": ["python", "ml", "nlp"]})
        result = FieldIndexHelpers.resolve_field_text("tags", chunk, {})
        assert result == "python,ml,nlp"

    def test_derived_meta_over_empty_doc_meta(self) -> None:
        """derived_meta is used even when doc_meta is empty."""
        chunk = _chunk(derived_meta={"entity": "OpenAI"})
        result = FieldIndexHelpers.resolve_field_text("entity", chunk, {})
        assert result == "OpenAI"


# ─── Chunk-provenance hardcoded fields (level 1) ──────────────────────────────

class TestChunkProvenanceFields:
    """Chunk-level hardcoded fields (heading_path, page, block_type, token_count) still resolve."""

    def test_heading_path_from_prov(self) -> None:
        chunk = _chunk(prov={"heading_path": "Section 2 > Results"})
        assert FieldIndexHelpers.resolve_field_text("heading_path", chunk, {}) == "Section 2 > Results"

    def test_page_from_prov(self) -> None:
        chunk = _chunk(prov={"pages": [3]})
        assert FieldIndexHelpers.resolve_field_text("page", chunk, {}) == "3"

    def test_block_type_from_prov(self) -> None:
        chunk = _chunk(prov={"block_types": ["paragraph", "table"]})
        assert FieldIndexHelpers.resolve_field_text("block_type", chunk, {}) == "paragraph,table"

    def test_token_count_from_chunk(self) -> None:
        chunk = _chunk()
        chunk.token_count = 42
        assert FieldIndexHelpers.resolve_field_text("token_count", chunk, {}) == "42"

    def test_hardcoded_field_not_overridden_by_derived_meta(self) -> None:
        """derived_meta cannot override a chunk-provenance hardcoded field (level-1 guard)."""
        # heading_path is resolved at level 1 before derived_meta is checked.
        chunk = _chunk(
            prov={"heading_path": "Real Heading"},
            derived_meta={"heading_path": "Should Not Win"},
        )
        # heading_path is handled at level 1 — derived_meta check happens at level 2.
        result = FieldIndexHelpers.resolve_field_text("heading_path", chunk, {})
        assert result == "Real Heading"


# ─── Document-scope resolution (level 3) ──────────────────────────────────────

class TestDocMetaFallback:
    """doc_meta is the final fallback when derived_meta and prov are both silent."""

    def test_doc_scope_field_from_doc_meta(self) -> None:
        chunk = _chunk()
        doc_meta = {"language": "en"}
        assert FieldIndexHelpers.resolve_field_text("language", chunk, doc_meta) == "en"

    def test_absent_field_returns_none(self) -> None:
        chunk = _chunk()
        result = FieldIndexHelpers.resolve_field_text("nonexistent_field", chunk, {})
        assert result is None

    def test_doc_meta_none_value_returns_none(self) -> None:
        chunk = _chunk()
        result = FieldIndexHelpers.resolve_field_text("kw", chunk, {"kw": None})
        assert result is None

    def test_doc_meta_list_value_comma_joined(self) -> None:
        chunk = _chunk()
        result = FieldIndexHelpers.resolve_field_text("tags", chunk, {"tags": ["a", "b"]})
        assert result == "a,b"
