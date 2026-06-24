# ====== Code Summary ======
# Unit tests for the IR domain layer: Chunk dataclass and DocumentIR Pydantic model.
# No I/O, no DB, no env vars beyond what conftest.py sets.

import pytest

from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models.document_ir import DocumentIR


# ── Chunk ─────────────────────────────────────────────────────────────────────


class TestChunk:
    """Tests for the Chunk dataclass (core retrieval unit)."""

    def test_create_minimal(self) -> None:
        """A chunk with required fields can be constructed without optional ones."""
        chunk = Chunk(
            id="chunk-001",
            document_id="doc-001",
            config_hash="deadbeef",
            block_ids=["b1", "b2"],
            raw_text="Hello world.",
            embed_text="Introduction\nHello world.",
            token_count=3,
            strategy="text",
        )
        assert chunk.id == "chunk-001"
        assert chunk.document_id == "doc-001"
        assert chunk.parent_id is None
        assert chunk.prov == {}

    def test_parent_id_optional(self) -> None:
        """parent_id defaults to None for flat/leaf chunks."""
        chunk = Chunk(
            id="child",
            document_id="doc-x",
            config_hash="h",
            block_ids=[],
            raw_text="text",
            embed_text="text",
            token_count=1,
            strategy="text",
            parent_id=None,
        )
        assert chunk.parent_id is None

    def test_hierarchical_parent(self) -> None:
        """A child chunk can reference a parent chunk by id."""
        parent = Chunk(
            id="parent-001",
            document_id="doc-001",
            config_hash="h",
            block_ids=["b1", "b2", "b3"],
            raw_text="Full section text",
            embed_text="Section\nFull section text",
            token_count=10,
            strategy="hierarchical_section_parent",
        )
        child = Chunk(
            id="child-001",
            document_id="doc-001",
            config_hash="h",
            block_ids=["b1"],
            raw_text="First paragraph",
            embed_text="Section\nFirst paragraph",
            token_count=4,
            strategy="hierarchical_section_child",
            parent_id=parent.id,
        )
        assert child.parent_id == parent.id
        assert parent.parent_id is None

    def test_prov_dict(self) -> None:
        """Provenance metadata can carry page numbers and heading path."""
        chunk = Chunk(
            id="c",
            document_id="d",
            config_hash="h",
            block_ids=["b1"],
            raw_text="text",
            embed_text="text",
            token_count=1,
            strategy="text",
            prov={"pages": [0, 1], "heading_path": "Intro > Background"},
        )
        assert chunk.prov["pages"] == [0, 1]
        assert chunk.prov["heading_path"] == "Intro > Background"

    def test_block_ids_order_preserved(self) -> None:
        """block_ids preserves insertion order (used for stable UUID derivation)."""
        ids = ["b3", "b1", "b2"]
        chunk = Chunk(
            id="c",
            document_id="d",
            config_hash="h",
            block_ids=ids,
            raw_text="x",
            embed_text="x",
            token_count=1,
            strategy="text",
        )
        assert chunk.block_ids == ["b3", "b1", "b2"]


# ── DocumentIR ────────────────────────────────────────────────────────────────


class TestDocumentIR:
    """Tests for the DocumentIR Pydantic model (canonical document representation)."""

    def test_create_minimal(self) -> None:
        """DocumentIR can be created with only required fields."""
        ir = DocumentIR(
            doc_id="doc-001",
            source_hash="a" * 64,
            n_pages=1,
            language="en",
        )
        assert ir.doc_id == "doc-001"
        assert ir.title == ""
        assert ir.blocks == []
        assert ir.quality_score is None
        assert ir.chain_traces == []

    def test_pipeline_fingerprints_default_empty(self) -> None:
        """pipeline_fingerprints starts empty and can be updated."""
        ir = DocumentIR(
            doc_id="doc-002",
            source_hash="b" * 64,
            n_pages=3,
            language="fr",
        )
        assert ir.pipeline_fingerprints == {}

    def test_with_title_and_quality(self) -> None:
        """Title and quality_score are optional but accepted."""
        ir = DocumentIR(
            doc_id="doc-003",
            source_hash="c" * 64,
            n_pages=5,
            language="en",
            title="My Research Paper",
            quality_score=0.87,
        )
        assert ir.title == "My Research Paper"
        assert ir.quality_score == pytest.approx(0.87)

    def test_quality_score_bounds(self) -> None:
        """quality_score must be between 0.0 and 1.0."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentIR(
                doc_id="doc-err",
                source_hash="d" * 64,
                n_pages=1,
                language="en",
                quality_score=1.5,  # invalid
            )

    def test_serialisation_roundtrip(self) -> None:
        """model_dump() / model_validate() round-trips without data loss."""
        ir = DocumentIR(
            doc_id="doc-rt",
            source_hash="e" * 64,
            n_pages=2,
            language="de",
            title="Rundreise",
            pipeline_fingerprints={"s0": "fp0", "s1": "fp1"},
        )
        dumped = ir.model_dump()
        restored = DocumentIR.model_validate(dumped)
        assert restored.doc_id == ir.doc_id
        assert restored.pipeline_fingerprints == ir.pipeline_fingerprints
        assert restored.language == ir.language
