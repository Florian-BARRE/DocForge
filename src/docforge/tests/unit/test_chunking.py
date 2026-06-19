# ====== Code Summary ======
# Unit tests for the refactored S4 chunking engine: split methods (token_budget / semantic /
# sentence_window), atomic-block handling (caption co-location, figure folding), hierarchical
# parent/child emission, cross-reference linking, and the ChunkConfig legacy migration.

import uuid

import pytest

from libs.core.ir.chunk import Chunk
from libs.core.ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
    TableData,
)
from libs.core.contracts.pipeline_config import AtomicConfig, ChunkConfig, PipelineConfig
from libs.engine.stages.chunking import (
    ChunkingHelpers,
    CrossReferenceLinker,
    SemanticSplitter,
    SentenceWindowSplitter,
    TokenBudgetSplitter,
)
from libs.engine.stages.s4_chunk import S4ChunkStage
from libs.capabilities.interfaces import EmbedResult

_BBOX = (0.0, 0.0, 1.0, 0.1)


# ─── IR builders ─────────────────────────────────────────────────────────────────


def _prov(page: int = 0) -> Provenance:
    return Provenance(page=page, bbox=_BBOX)


def _para(text: str, block_id: str | None = None, ro: int = 0) -> Block:
    return Block(id=block_id or str(uuid.uuid4()), type=BlockType.PARAGRAPH, text=text, prov=_prov(), reading_order=ro)


def _formula(text: str, block_id: str | None = None) -> Block:
    return Block(id=block_id or str(uuid.uuid4()), type=BlockType.FORMULA, text=text, prov=_prov(), reading_order=0)


def _caption(text: str, block_id: str | None = None) -> Block:
    return Block(id=block_id or str(uuid.uuid4()), type=BlockType.CAPTION, text=text, prov=_prov(), reading_order=0)


def _figure(description: str, block_id: str | None = None, kind: FigureKind = FigureKind.CHART) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.FIGURE,
        prov=_prov(page=1),
        reading_order=0,
        figure=FigureEnrichment(kind=kind, crop_key="fig/x.png", relevance=0.9, description=description),
    )


def _table(block_id: str | None = None) -> Block:
    return Block(
        id=block_id or str(uuid.uuid4()),
        type=BlockType.TABLE,
        prov=_prov(page=2),
        reading_order=0,
        table=TableData(cells=[["A", "B"], ["1", "2"]], n_rows=2, n_cols=2, has_header=True),
    )


def _ir(blocks: list[Block], doc_id: str | None = None) -> DocumentIR:
    return DocumentIR(
        doc_id=doc_id or str(uuid.uuid4()),
        title="Doc",
        source_hash="sha",
        n_pages=3,
        language="en",
        blocks=blocks,
    )


# ─── Fake embedding providers (semantic splitter) ─────────────────────────────────


class _FakeEmbed:
    """Returns preset dense vectors in input order (one per text)."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors

    async def embed(self, texts: list[str]) -> EmbedResult:
        return EmbedResult(vectors=self._vectors[: len(texts)], sparse=None, model="fake")


class _RaisingEmbed:
    """Simulates a TEI outage so the semantic splitter must fall back."""

    async def embed(self, texts: list[str]) -> EmbedResult:
        raise RuntimeError("TEI down")


# ─── TokenBudgetSplitter ──────────────────────────────────────────────────────────


class TestTokenBudgetSplitter:
    @pytest.mark.asyncio
    async def test_splits_on_budget(self) -> None:
        splitter = TokenBudgetSplitter(max_tokens=5, overlap_blocks=0)
        blocks = [_para("word " * 20), _para("word " * 20)]
        pieces = await splitter.split_section(blocks)
        assert len(pieces) == 2

    @pytest.mark.asyncio
    async def test_formula_stays_with_intro(self) -> None:
        """A FORMULA never starts a new piece — it stays attached to the previous block."""
        splitter = TokenBudgetSplitter(max_tokens=8, overlap_blocks=0, atomic_formulas=True)
        intro = _para("word " * 20, block_id="intro")
        formula = _formula("E = mc^2", block_id="f1")
        pieces = await splitter.split_section([intro, formula])
        # The formula must land in the same piece as its introducing paragraph.
        piece_with_formula = [p for p in pieces if "f1" in p.block_ids][0]
        assert "intro" in piece_with_formula.block_ids


# ─── SentenceWindowSplitter ───────────────────────────────────────────────────────


class TestSentenceWindowSplitter:
    @pytest.mark.asyncio
    async def test_overlapping_windows(self) -> None:
        splitter = SentenceWindowSplitter(window_sentences=2, stride_sentences=1)
        block = _para("One. Two. Three. Four.", block_id="b")
        pieces = await splitter.split_section([block])
        # 4 sentences, window 2, stride 1 → windows [1,2],[2,3],[3,4] = 3 pieces
        assert len(pieces) == 3
        assert "Two" in pieces[0].text and "Two" in pieces[1].text  # overlap

    @pytest.mark.asyncio
    async def test_single_window_when_short(self) -> None:
        splitter = SentenceWindowSplitter(window_sentences=5, stride_sentences=4)
        pieces = await splitter.split_section([_para("Only one sentence.")])
        assert len(pieces) == 1


# ─── SemanticSplitter ─────────────────────────────────────────────────────────────


class TestSemanticSplitter:
    @pytest.mark.asyncio
    async def test_cuts_at_distance_peak(self) -> None:
        # b0,b1 identical direction; b2 orthogonal → one boundary before b2.
        embed = _FakeEmbed([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        splitter = SemanticSplitter(embed, max_tokens=10_000, min_tokens=0, breakpoint_percentile=90)
        blocks = [_para("alpha", "b0"), _para("alpha two", "b1"), _para("beta", "b2")]
        pieces = await splitter.split_section(blocks)
        assert len(pieces) == 2
        assert pieces[0].block_ids == ["b0", "b1"]
        assert pieces[1].block_ids == ["b2"]

    @pytest.mark.asyncio
    async def test_fallback_on_embedding_failure(self) -> None:
        splitter = SemanticSplitter(_RaisingEmbed(), max_tokens=5, min_tokens=0)
        blocks = [_para("word " * 20), _para("word " * 20)]
        pieces = await splitter.split_section(blocks)
        # Degrades to a token-budget split rather than failing.
        assert len(pieces) == 2


# ─── CrossReferenceLinker ─────────────────────────────────────────────────────────


class TestCrossReferenceLinker:
    def test_links_text_to_figure(self) -> None:
        fig = Chunk(
            id="figc", document_id="d", config_hash="h", block_ids=["f"],
            raw_text="Figure 1: Revenue chart", embed_text="", token_count=3, strategy="figure",
            prov={"heading_path": ""},
        )
        txt = Chunk(
            id="txtc", document_id="d", config_hash="h", block_ids=["t"],
            raw_text="See Figure 1 for the trend.", embed_text="", token_count=5, strategy="token_budget",
            prov={"heading_path": "Results"},
        )
        n = CrossReferenceLinker().link([fig, txt])
        assert n == 1
        assert txt.prov["linked_chunk_ids"] == ["figc"]
        assert "linked_chunk_ids" not in fig.prov  # the figure references nothing

    def test_no_self_link(self) -> None:
        fig = Chunk(
            id="figc", document_id="d", config_hash="h", block_ids=["f"],
            raw_text="Figure 1: see Figure 1", embed_text="", token_count=3, strategy="figure",
            prov={},
        )
        CrossReferenceLinker().link([fig])
        assert "linked_chunk_ids" not in fig.prov


# ─── S4 — atomic blocks (Axe 3) ───────────────────────────────────────────────────


class TestS4Atomic:
    @pytest.mark.asyncio
    async def test_caption_colocated_with_figure(self) -> None:
        stage = S4ChunkStage()  # defaults: atomic figures + keep_caption_with_figure
        fig = _figure("a bar chart", block_id="fig")
        cap = _caption("Figure 2: Quarterly revenue", block_id="cap")
        result = await stage.run(_ir([fig, cap]))
        fig_chunks = [c for c in result.chunks if c.strategy == "figure"]
        assert len(fig_chunks) == 1
        assert "Figure 2" in fig_chunks[0].raw_text          # caption folded in
        assert "cap" in fig_chunks[0].block_ids               # caption block consumed
        # No standalone caption text chunk was produced
        assert all(c.strategy == "figure" for c in result.chunks)

    @pytest.mark.asyncio
    async def test_non_atomic_figure_folds_into_text(self) -> None:
        atomic = AtomicConfig(tables=True, figures=False, formulas=True, keep_caption_with_figure=False)
        stage = S4ChunkStage(atomic=atomic)
        result = await stage.run(_ir([_para("Intro paragraph."), _figure("an embedded chart")]))
        assert result.n_figure_chunks == 0
        assert any("embedded chart" in c.raw_text for c in result.chunks)

    @pytest.mark.asyncio
    async def test_table_atomic_by_default(self) -> None:
        result = await S4ChunkStage().run(_ir([_table(block_id="tbl")]))
        assert result.n_table_chunks == 1


# ─── S4 — hierarchical mode (Axe 1) ───────────────────────────────────────────────


class TestS4Hierarchical:
    @pytest.mark.asyncio
    async def test_parent_and_children_emitted(self) -> None:
        stage = S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=5), hierarchical=True)
        blocks = [_para("word " * 20, "p0"), _para("word " * 20, "p1"), _para("word " * 20, "p2")]
        result = await stage.run(_ir(blocks))

        parents = [c for c in result.chunks if c.strategy == "section_parent"]
        children = [c for c in result.chunks if c.parent_id is not None]
        assert len(parents) == 1
        assert result.n_parent_chunks == 1
        assert len(children) >= 2
        # Every child points at the section parent; the parent has no parent.
        assert all(c.parent_id == parents[0].id for c in children)
        assert parents[0].parent_id is None

    @pytest.mark.asyncio
    async def test_small_section_stays_flat(self) -> None:
        """A section that fits the budget yields a single flat chunk (no redundant parent)."""
        stage = S4ChunkStage(splitter=TokenBudgetSplitter(max_tokens=512), hierarchical=True)
        result = await stage.run(_ir([_para("short text")]))
        assert result.n_parent_chunks == 0
        assert all(c.parent_id is None for c in result.chunks)


# ─── S4 — cross-reference integration ─────────────────────────────────────────────


class TestS4CrossReferences:
    @pytest.mark.asyncio
    async def test_text_links_to_figure_after_run(self) -> None:
        stage = S4ChunkStage(cross_references=True)
        blocks = [
            _para("See Figure 1 for the breakdown.", "t"),
            _figure("a chart", "fig"),
            _caption("Figure 1: Breakdown", "cap"),
        ]
        result = await stage.run(_ir(blocks))
        fig_chunk = [c for c in result.chunks if c.strategy == "figure"][0]
        txt_chunk = [c for c in result.chunks if c.strategy != "figure"][0]
        assert txt_chunk.prov.get("linked_chunk_ids") == [fig_chunk.id]

    @pytest.mark.asyncio
    async def test_cross_references_disabled(self) -> None:
        stage = S4ChunkStage(cross_references=False)
        blocks = [_para("See Figure 1.", "t"), _figure("chart", "fig"), _caption("Figure 1: X", "cap")]
        result = await stage.run(_ir(blocks))
        assert all("linked_chunk_ids" not in c.prov for c in result.chunks)


# ─── ChunkConfig legacy migration ─────────────────────────────────────────────────


class TestChunkConfig:
    def test_shape_passthrough(self) -> None:
        cfg = PipelineConfig.from_dict(
            {"chunk": {"split_method": {"id": "sentence_window", "params": {"window_sentences": 3}}}}
        )
        assert cfg.chunk.split_method.id == "sentence_window"
        assert cfg.chunk.split_method.window_sentences == 3

    def test_defaults(self) -> None:
        cfg = ChunkConfig()
        assert cfg.split_method.id == "token_budget"
        assert cfg.hierarchical is False
        assert cfg.cross_references is True
        assert cfg.atomic.tables is True


# ─── Helpers ──────────────────────────────────────────────────────────────────────


class TestChunkingHelpers:
    def test_stable_uuid_changes_with_ordinal(self) -> None:
        a = ChunkingHelpers.stable_chunk_uuid("d", ["b"], "h", 0)
        b = ChunkingHelpers.stable_chunk_uuid("d", ["b"], "h", 1)
        assert a != b

    def test_split_sentences(self) -> None:
        assert ChunkingHelpers.split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
