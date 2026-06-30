# ====== Code Summary ======
# Unit tests for S4 ChunkingHelpers: token estimation, stable UUID derivation,
# block-to-text rendering, and provenance aggregation.
# No I/O; all tests are pure and synchronous.

import pytest

from common_libs.domain.ir.models.block import Block
from common_libs.domain.ir.models.enums import BlockType
from common_libs.domain.ir.models.provenance import Provenance
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker.text_helpers import (
    ChunkingHelpers,
)


def _prov(page: int = 0) -> Provenance:
    """Build a minimal Provenance fixture for a given page."""
    return Provenance(page=page, bbox=(0.0, 0.0, 1.0, 0.05))


def _block(
    block_id: str,
    block_type: BlockType = BlockType.PARAGRAPH,
    text: str = "sample text",
    page: int = 0,
    level: int | None = None,
) -> Block:
    """Build a minimal Block fixture."""
    return Block(
        id=block_id,
        type=block_type,
        prov=_prov(page),
        reading_order=0,
        text=text,
        level=level,
    )


# ── Token estimation ──────────────────────────────────────────────────────────


class TestEstimateTokensText:
    """Tests for ChunkingHelpers.estimate_tokens_text."""

    def test_typical_text(self) -> None:
        """100 chars should produce 25 tokens (chars/4 heuristic)."""
        assert ChunkingHelpers.estimate_tokens_text("a" * 100) == 25

    def test_short_text_floored_to_one(self) -> None:
        """Even a single char returns at least 1 token (never 0)."""
        assert ChunkingHelpers.estimate_tokens_text("x") == 1

    def test_empty_string_floored_to_one(self) -> None:
        """Empty string returns 1 — keeps downstream math safe (no divide-by-zero)."""
        assert ChunkingHelpers.estimate_tokens_text("") == 1

    def test_four_char_word(self) -> None:
        """Exactly 4 chars → 1 token."""
        assert ChunkingHelpers.estimate_tokens_text("word") == 1

    def test_eight_char_text(self) -> None:
        """8 chars → 2 tokens."""
        assert ChunkingHelpers.estimate_tokens_text("abcdefgh") == 2

    def test_large_text(self) -> None:
        """400-char text → 100 tokens."""
        assert ChunkingHelpers.estimate_tokens_text("z" * 400) == 100


# ── Stable chunk UUID ─────────────────────────────────────────────────────────


class TestStableChunkUuid:
    """Tests for ChunkingHelpers.stable_chunk_uuid."""

    def test_deterministic(self) -> None:
        """Same inputs always produce the same UUID."""
        uid1 = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1", "b2"], "cfg-abc", 0)
        uid2 = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1", "b2"], "cfg-abc", 0)
        assert uid1 == uid2

    def test_different_ordinal(self) -> None:
        """Changing ordinal alone must change the UUID (tie-breaker for overlapping windows)."""
        uid0 = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1"], "cfg-abc", 0)
        uid1 = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1"], "cfg-abc", 1)
        assert uid0 != uid1

    def test_different_doc_id(self) -> None:
        """Different doc_id must produce a different UUID."""
        uid_a = ChunkingHelpers.stable_chunk_uuid("doc-A", ["b1"], "cfg", 0)
        uid_b = ChunkingHelpers.stable_chunk_uuid("doc-B", ["b1"], "cfg", 0)
        assert uid_a != uid_b

    def test_different_block_ids(self) -> None:
        """Different block_ids must produce a different UUID."""
        uid_x = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1", "b2"], "cfg", 0)
        uid_y = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1", "b3"], "cfg", 0)
        assert uid_x != uid_y

    def test_different_config_hash(self) -> None:
        """Different config_hash must produce a different UUID (pipeline config matters)."""
        uid_c1 = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1"], "cfg-v1", 0)
        uid_c2 = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1"], "cfg-v2", 0)
        assert uid_c1 != uid_c2

    def test_returns_valid_uuid_string(self) -> None:
        """Return value must be parseable as a UUID."""
        import uuid as uuid_mod

        uid = ChunkingHelpers.stable_chunk_uuid("doc-1", ["b1"], "cfg", 0)
        parsed = uuid_mod.UUID(uid)
        assert str(parsed) == uid


# ── block_to_text ─────────────────────────────────────────────────────────────


class TestBlockToText:
    """Tests for ChunkingHelpers.block_to_text."""

    def test_paragraph(self) -> None:
        """PARAGRAPH returns raw text unchanged."""
        block = _block("p1", BlockType.PARAGRAPH, "Hello world.")
        assert ChunkingHelpers.block_to_text(block) == "Hello world."

    def test_list_item(self) -> None:
        """LIST_ITEM is prefixed with '- '."""
        block = _block("li1", BlockType.LIST_ITEM, "First item")
        assert ChunkingHelpers.block_to_text(block) == "- First item"

    def test_code_block(self) -> None:
        """CODE is wrapped in triple backticks."""
        block = _block("c1", BlockType.CODE, "print('hi')")
        result = ChunkingHelpers.block_to_text(block)
        assert result == "```\nprint('hi')\n```"

    def test_heading_h2(self) -> None:
        """HEADING with level=2 is prefixed with '## '."""
        block = _block("h1", BlockType.HEADING, "My Section", level=2)
        assert ChunkingHelpers.block_to_text(block) == "## My Section"

    def test_heading_default_level(self) -> None:
        """HEADING with level=None falls back to '#' (H1)."""
        block = _block("h2", BlockType.HEADING, "Top Level", level=None)
        assert ChunkingHelpers.block_to_text(block) == "# Top Level"

    def test_empty_paragraph(self) -> None:
        """Empty text returns empty string."""
        block = _block("p2", BlockType.PARAGRAPH, "")
        assert ChunkingHelpers.block_to_text(block) == ""


# ── aggregate_prov ────────────────────────────────────────────────────────────


class TestAggregateProv:
    """Tests for ChunkingHelpers.aggregate_prov."""

    def test_single_block(self) -> None:
        """Single block provenance includes its page, type, and heading path."""
        block = _block("b1", BlockType.PARAGRAPH, page=2)
        prov = ChunkingHelpers.aggregate_prov([block], heading_path="Intro > Background")
        assert prov["pages"] == [2]
        assert prov["block_count"] == 1
        assert "paragraph" in prov["block_types"]
        assert prov["heading_path"] == "Intro > Background"

    def test_multi_page_deduped(self) -> None:
        """Multiple blocks on the same page deduplicate the pages list."""
        blocks = [_block("b1", page=0), _block("b2", page=0), _block("b3", page=1)]
        prov = ChunkingHelpers.aggregate_prov(blocks, heading_path="")
        assert prov["pages"] == [0, 1]
        assert prov["block_count"] == 3

    def test_mixed_types_sorted(self) -> None:
        """Mixed block types are sorted in the output."""
        blocks = [_block("b1", BlockType.PARAGRAPH), _block("b2", BlockType.HEADING, level=2)]
        prov = ChunkingHelpers.aggregate_prov(blocks, heading_path="")
        assert sorted(prov["block_types"]) == prov["block_types"]
