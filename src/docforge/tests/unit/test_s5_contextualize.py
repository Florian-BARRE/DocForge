# ====== Code Summary ======
# Unit tests for the S5 contextualization stage.
# S5 reads the heading breadcrumb from chunk.prov["heading_path"] (set by S4).

import uuid

import pytest

from ir.chunk import Chunk
from ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
    TableData,
)
from pipeline.stages.s5_contextualize import S5ContextualizeStage


# ─── Helpers ────────────────────────────────────────────────────────────────────

_BBOX = (0.0, 0.0, 1.0, 0.1)


def _block(
    block_type: BlockType = BlockType.PARAGRAPH,
    text: str = "sample text",
    level: int | None = None,
    block_id: str | None = None,
    reading_order: int = 0,
) -> Block:
    """Construct a minimal Block for testing."""
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=block_type,
        text=text,
        level=level,
        prov=Provenance(page=0, bbox=_BBOX),
        reading_order=reading_order,
    )


def _chunk(block_ids: list[str], strategy: str = "recursive_structure_aware") -> Chunk:
    """Construct a minimal Chunk for testing."""
    return Chunk(
        id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        config_hash="cfghash",
        block_ids=block_ids,
        raw_text="raw text",
        embed_text="",
        token_count=5,
        strategy=strategy,
    )


def _ir(blocks: list[Block], title: str = "Test Doc") -> DocumentIR:
    """Construct a minimal DocumentIR for testing."""
    return DocumentIR(
        doc_id=str(uuid.uuid4()),
        title=title,
        source_hash="sha256testfixture",
        n_pages=1,
        language="en",
        blocks=blocks,
    )


# ─── Tests: S5ContextualizeStage ────────────────────────────────────────────────


class TestS5ContextualizeStage:
    """Tests for the full S5 stage run() method."""

    @pytest.fixture
    def stage(self) -> S5ContextualizeStage:
        return S5ContextualizeStage()

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_zero_contextualized(
        self, stage: S5ContextualizeStage
    ) -> None:
        ir = _ir([])
        result = await stage.run([], ir)
        assert result.chunks == []
        assert result.n_contextualized == 0

    @pytest.mark.asyncio
    async def test_embed_text_filled_on_chunk(self, stage: S5ContextualizeStage) -> None:
        """Each chunk should have embed_text set after S5."""
        blk_id = str(uuid.uuid4())
        block = _block(BlockType.PARAGRAPH, text="Some paragraph text.", block_id=blk_id)
        ir = _ir([block], title="My Document")
        chunk = _chunk([blk_id])
        chunk.raw_text = "Some paragraph text."

        result = await stage.run([chunk], ir)
        assert result.n_contextualized == 1
        assert "My Document" in result.chunks[0].embed_text
        assert "Some paragraph text." in result.chunks[0].embed_text

    @pytest.mark.asyncio
    async def test_heading_breadcrumb_included_in_embed_text(
        self, stage: S5ContextualizeStage
    ) -> None:
        """Breadcrumb from prov['heading_path'] (set by S4) is prepended to embed_text."""
        txt_id = str(uuid.uuid4())
        block = _block(BlockType.PARAGRAPH, text="See Figure 1.", block_id=txt_id)
        ir = _ir([block], title="Report")
        chunk = _chunk([txt_id])
        chunk.raw_text = "See Figure 1."
        # S4 sets heading_path on the chunk prov before S5 runs
        chunk.prov["heading_path"] = "Results"

        result = await stage.run([chunk], ir)
        embed = result.chunks[0].embed_text
        assert "Results" in embed
        assert "See Figure 1." in embed

    @pytest.mark.asyncio
    async def test_multiple_chunks_all_contextualized(
        self, stage: S5ContextualizeStage
    ) -> None:
        """All chunks in a batch receive embed_text."""
        blocks = [_block(block_id=f"b{i}") for i in range(3)]
        ir = _ir(blocks)
        chunks = [_chunk([f"b{i}"]) for i in range(3)]
        for i, c in enumerate(chunks):
            c.raw_text = f"Text {i}"

        result = await stage.run(chunks, ir)
        assert result.n_contextualized == 3
        for chunk in result.chunks:
            assert chunk.embed_text != ""

    @pytest.mark.asyncio
    async def test_missing_block_in_index_produces_empty_breadcrumb(
        self, stage: S5ContextualizeStage
    ) -> None:
        """A chunk referencing an unknown block_id degrades gracefully."""
        ir = _ir([], title="Doc")
        chunk = _chunk(["nonexistent_block_id"])
        chunk.raw_text = "orphan text"

        result = await stage.run([chunk], ir)
        # embed_text should contain at least the title
        assert "Doc" in result.chunks[0].embed_text

    @pytest.mark.asyncio
    async def test_table_strategy_chunk(self, stage: S5ContextualizeStage) -> None:
        """Table chunks embed their raw_text (cells assembled by S4) plus the title."""
        blk_id = str(uuid.uuid4())
        table_block = Block(
            id=blk_id,
            type=BlockType.TABLE,
            prov=Provenance(page=0, bbox=_BBOX),
            reading_order=0,
            table=TableData(cells=[["Col A", "Col B"], ["1", "2"]], n_rows=2, n_cols=2, has_header=True),
        )
        ir = _ir([table_block], title="Stats")
        chunk = _chunk([blk_id], strategy="table")
        # S4 already rendered the table cells into raw_text; S5 uses that verbatim.
        chunk.raw_text = "Col A | Col B\n1 | 2"

        result = await stage.run([chunk], ir)
        embed = result.chunks[0].embed_text
        assert "Col A" in embed
        assert "Stats" in embed
