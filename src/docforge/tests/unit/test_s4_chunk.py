# ====== Code Summary ======
# Unit tests for S4ChunkStage — structure-aware recursive chunker.
# Tests block routing, figure/table isolation, token splitting, and UUID stability.

import uuid

import pytest

from ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
    TableData,
)
from pipeline.stages.chunking import TokenBudgetSplitter
from pipeline.stages.s4_chunk import S4ChunkStage


# ─── IR helpers ──────────────────────────────────────────────────────────────────

_BBOX = (0.0, 0.0, 1.0, 0.1)


def _prov(page: int = 0) -> Provenance:
    return Provenance(page=page, bbox=_BBOX)


def _text_block(
    text: str = "Lorem ipsum dolor.",
    block_id: str | None = None,
    reading_order: int = 0,
) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.PARAGRAPH,
        text=text,
        prov=_prov(),
        reading_order=reading_order,
    )


def _heading_block(
    text: str = "Chapter 1",
    level: int = 1,
    block_id: str | None = None,
    reading_order: int = 0,
) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.HEADING,
        text=text,
        level=level,
        prov=_prov(),
        reading_order=reading_order,
    )


def _figure_block(kind: str = "photo", block_id: str | None = None) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.FIGURE,
        prov=_prov(page=1),
        reading_order=0,
        figure=FigureEnrichment(kind=FigureKind.PHOTO, crop_key="fig/test.png", relevance=0.9),
    )


def _decorative_block(block_id: str | None = None) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.FIGURE,
        prov=_prov(),
        reading_order=0,
        figure=FigureEnrichment(kind=FigureKind.DECORATIVE, crop_key="fig/deco.png", relevance=0.1),
    )


def _table_block(cells: list[list[str]] | None = None, block_id: str | None = None) -> Block:
    _cells = cells or [["A", "B"], ["1", "2"]]
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.TABLE,
        prov=_prov(page=2),
        reading_order=0,
        table=TableData(
            cells=_cells,
            n_rows=len(_cells),
            n_cols=len(_cells[0]) if _cells else 0,
            has_header=True,
        ),
    )


def _header_footer_block(block_id: str | None = None) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.HEADER_FOOTER,
        text="Page 1",
        prov=_prov(),
        reading_order=0,
    )


def _ir(blocks: list[Block], doc_id: str | None = None) -> DocumentIR:
    return DocumentIR(
        doc_id=doc_id or str(uuid.uuid4()),
        title="Test Doc",
        source_hash="sha256testfixture",
        n_pages=3,
        language="en",
        blocks=blocks,
    )


# ─── Stage fixture ────────────────────────────────────────────────────────────────


@pytest.fixture
def stage() -> S4ChunkStage:
    """Default stage: token_budget split, max_tokens=512, no overlap."""
    return S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=512, overlap_blocks=0))


@pytest.fixture
def tight_stage() -> S4ChunkStage:
    """Very small token budget — forces splitting on multi-block inputs."""
    return S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=5, overlap_blocks=0))


# ─── Tests ───────────────────────────────────────────────────────────────────────


class TestS4ChunkStage:

    @pytest.mark.asyncio
    async def test_empty_ir_produces_no_chunks(self, stage: S4ChunkStage) -> None:
        result = await stage.run(_ir([]))
        assert result.chunks == []
        assert result.n_text_chunks == 0
        assert result.n_figure_chunks == 0
        assert result.n_table_chunks == 0

    @pytest.mark.asyncio
    async def test_single_text_block_produces_one_chunk(self, stage: S4ChunkStage) -> None:
        block = _text_block("Hello world.")
        result = await stage.run(_ir([block]))
        assert len(result.chunks) == 1
        assert result.n_text_chunks == 1
        assert "Hello world." in result.chunks[0].raw_text

    @pytest.mark.asyncio
    async def test_header_footer_blocks_are_skipped(self, stage: S4ChunkStage) -> None:
        """HEADER_FOOTER blocks must never appear in any chunk."""
        blocks = [_header_footer_block(), _text_block("content")]
        result = await stage.run(_ir(blocks))
        # No chunk should reference the HEADER_FOOTER block
        for chunk in result.chunks:
            for bid in chunk.block_ids:
                assert blocks[0].id not in chunk.block_ids

    @pytest.mark.asyncio
    async def test_decorative_figure_is_skipped(self, stage: S4ChunkStage) -> None:
        """DECORATIVE figures must be silently excluded."""
        blocks = [_decorative_block(), _text_block("visible")]
        result = await stage.run(_ir(blocks))
        assert result.n_figure_chunks == 0
        # Only the text block should appear
        all_block_ids = [bid for c in result.chunks for bid in c.block_ids]
        assert blocks[0].id not in all_block_ids

    @pytest.mark.asyncio
    async def test_figure_block_produces_figure_chunk(self, stage: S4ChunkStage) -> None:
        """Non-decorative FIGURE blocks produce exactly one figure chunk each."""
        block = _figure_block(kind="photo")
        result = await stage.run(_ir([block]))
        assert result.n_figure_chunks == 1
        fig_chunks = [c for c in result.chunks if c.strategy == "figure"]
        assert len(fig_chunks) == 1
        assert block.id in fig_chunks[0].block_ids

    @pytest.mark.asyncio
    async def test_table_block_produces_table_chunk(self, stage: S4ChunkStage) -> None:
        """TABLE blocks produce exactly one table chunk each."""
        block = _table_block()
        result = await stage.run(_ir([block]))
        assert result.n_table_chunks == 1
        table_chunks = [c for c in result.chunks if c.strategy == "table"]
        assert len(table_chunks) == 1
        assert block.id in table_chunks[0].block_ids

    @pytest.mark.asyncio
    async def test_embed_text_is_empty_after_s4(self, stage: S4ChunkStage) -> None:
        """S4 sets embed_text to empty string — it is filled by S5."""
        result = await stage.run(_ir([_text_block()]))
        for chunk in result.chunks:
            assert chunk.embed_text == ""

    @pytest.mark.asyncio
    async def test_chunk_ids_are_stable(self, stage: S4ChunkStage) -> None:
        """Running S4 twice on the same IR produces identical chunk IDs."""
        blocks = [_heading_block(block_id="h1"), _text_block(block_id="t1")]
        ir = _ir(blocks, doc_id="doc-fixed")
        result1 = await stage.run(ir)
        result2 = await stage.run(ir)
        ids1 = {c.id for c in result1.chunks}
        ids2 = {c.id for c in result2.chunks}
        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_chunk_ids_are_unique(self, stage: S4ChunkStage) -> None:
        """Each chunk within a run has a distinct UUID."""
        blocks = [
            _heading_block(), _text_block(), _text_block(), _table_block(),
        ]
        result = await stage.run(_ir(blocks))
        ids = [c.id for c in result.chunks]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_config_hash_is_consistent(self) -> None:
        """Two stages with the same config must produce the same config_hash."""
        stage_a = S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=256, overlap_blocks=0))
        stage_b = S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=256, overlap_blocks=0))
        ir = _ir([_text_block()])
        res_a = await stage_a.run(ir)
        res_b = await stage_b.run(ir)
        assert res_a.config_hash == res_b.config_hash

    @pytest.mark.asyncio
    async def test_different_max_tokens_changes_config_hash(self) -> None:
        """Changing max_tokens must produce a different config_hash."""
        stage_a = S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=512))
        stage_b = S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=256))
        ir = _ir([_text_block()])
        res_a = await stage_a.run(ir)
        res_b = await stage_b.run(ir)
        assert res_a.config_hash != res_b.config_hash

    @pytest.mark.asyncio
    async def test_tight_token_budget_splits_blocks(self, tight_stage: S4ChunkStage) -> None:
        """When blocks exceed max_tokens they must be split into multiple chunks."""
        # Two blocks, each with ~50 tokens; max_tokens=5 → must produce 2+ chunks
        blocks = [
            _text_block("word " * 30, block_id="t1"),
            _text_block("word " * 30, block_id="t2"),
        ]
        result = await tight_stage.run(_ir(blocks))
        assert result.n_text_chunks >= 2

    @pytest.mark.asyncio
    async def test_document_id_on_all_chunks(self, stage: S4ChunkStage) -> None:
        """All chunks must carry the same document_id as the IR."""
        doc_id = str(uuid.uuid4())
        blocks = [_text_block(), _figure_block()]
        ir = _ir(blocks, doc_id=doc_id)
        result = await stage.run(ir)
        for chunk in result.chunks:
            assert chunk.document_id == doc_id

    @pytest.mark.asyncio
    async def test_prov_contains_pages(self, stage: S4ChunkStage) -> None:
        """Each chunk's prov dict must contain a non-empty 'pages' list."""
        result = await stage.run(_ir([_text_block()]))
        for chunk in result.chunks:
            assert "pages" in chunk.prov
            assert isinstance(chunk.prov["pages"], list)
            assert len(chunk.prov["pages"]) > 0

    @pytest.mark.asyncio
    async def test_token_count_is_positive(self, stage: S4ChunkStage) -> None:
        """token_count must be a positive integer for non-empty chunks."""
        result = await stage.run(_ir([_text_block("some text here")]))
        for chunk in result.chunks:
            assert chunk.token_count > 0
