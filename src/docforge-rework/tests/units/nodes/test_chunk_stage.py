"""Chunk stage: shared projection rules, the 3 methods (structure/fixed/semantic), family/blob
wiring, and the 5 audit fixes (cyclic parent, oversized atomic, run-on hard-cut, caption fusion).

Ported from the scratchpad's test_chunk_stage.py.
"""

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.chunk.base import BaseChunkerConfig, PassageProjector
from shared_libs.pipelines.ingest.nodes.chunk.base.io import ChunkerConsumes
from shared_libs.pipelines.ingest.nodes.chunk.fixed_size import (
    ChunkerFixedSizeConfig,
    ChunkerFixedSizeNode,
)
from shared_libs.pipelines.ingest.nodes.chunk.semantic import (
    ChunkerSemanticConfig,
    ChunkerSemanticNode,
)
from shared_libs.pipelines.ingest.nodes.chunk.structure_aware import (
    ChunkerStructureAwareConfig,
    ChunkerStructureAwareNode,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Block,
    BlockType,
    ChunkRole,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
    TableData,
    role_default_enabled,
)


def _blk(bid, btype, order, page=0, text=None, parent=None, level=None, table=None, figure=None) -> Block:
    return Block(id=bid, block_type=btype, reading_order=order, parent_id=parent, level=level,
                 provenance=Provenance(page=page, bbox=(0.1, 0.1, 0.9, 0.9)),
                 text=text, table=table, figure=figure)


LONG = " ".join(f"Sentence number {i} talks about the same important subject." for i in range(40))
IR = DocumentIR(doc_id="doc1", source_hash="h", n_pages=2, blocks=[
    _blk("h1", BlockType.HEADING, 0, text="Introduction", level=1),
    _blk("p1", BlockType.PARAGRAPH, 1, text="Cats are small felines. They purr loudly.", parent="h1"),
    _blk("fig1", BlockType.FIGURE, 2, text="Figure 1: a cat", parent="h1",
        figure=FigureEnrichment(description="A ginger cat sleeping.", ocr_text="CAT-01")),
    _blk("deco", BlockType.FIGURE, 3, parent="h1", figure=FigureEnrichment()),   # nothing to say
    _blk("hf", BlockType.HEADER_FOOTER, 4, text="Page 1 - Confidential"),        # excluded
    _blk("h2", BlockType.HEADING, 5, text="Results", level=1, page=1),
    _blk("t1", BlockType.TABLE, 6, parent="h2", page=1,
        table=TableData(cells=[["Metric", "Value"], ["Accuracy", "0.93"]], n_rows=2, n_cols=2, has_header=True)),
    _blk("p2", BlockType.PARAGRAPH, 7, text=LONG, parent="h2", page=1),
])


def test_shared_projection_composition_rules() -> None:
    passages = PassageProjector.project(IR, BaseChunkerConfig())
    by_first_block = {passage.block_ids[0]: passage for passage in passages}
    # Header/footer is no longer dropped — it is projected as a HEADER_FOOTER-role passage.
    assert [ps.block_ids[0] for ps in passages] == ["h1", "p1", "fig1", "hf", "h2", "t1", "p2"]

    fig = by_first_block["fig1"]
    assert fig.atomic
    assert fig.text.startswith("[Image:")           # explicit marker, not bare prose
    assert "Figure 1: a cat" in fig.text
    assert "ginger cat" in fig.text
    assert "[OCR] CAT-01" in fig.text                # OCR labelled distinctly from the description
    assert "deco" not in by_first_block             # empty/decorative figure still drops out

    # Header/footer is KEPT but structurally labelled (disabled-by-role downstream); body is body.
    assert by_first_block["hf"].role == ChunkRole.HEADER_FOOTER
    assert by_first_block["hf"].text == "Page 1 - Confidential"
    assert by_first_block["p1"].role == ChunkRole.BODY

    table = by_first_block["t1"]
    assert table.atomic
    assert "| Metric | Value |" in table.text
    assert "| --- | --- |" in table.text
    assert by_first_block["p2"].heading_path == ["Results"]
    assert by_first_block["p2"].section_key == ["h2"]
    assert by_first_block["h1"].section_key == ["h1"]  # a heading belongs to its own section


ROLE_IR = DocumentIR(doc_id="roles", source_hash="h", n_pages=2, blocks=[
    _blk("toc_h", BlockType.HEADING, 0, text="Table of Contents", level=1),
    _blk("toc_a", BlockType.LIST_ITEM, 1, text="1. Introduction .......... 1", parent="toc_h"),
    _blk("toc_b", BlockType.LIST_ITEM, 2, text="2. Results .......... 4", parent="toc_h"),
    _blk("hf0", BlockType.HEADER_FOOTER, 3, text="Confidential — page 1"),
    _blk("intro_h", BlockType.HEADING, 4, text="Introduction", level=1, page=1),
    _blk("intro_p", BlockType.PARAGRAPH, 5, text="Cats are small felines. They purr loudly.",
         parent="intro_h", page=1),
    _blk("hf1", BlockType.HEADER_FOOTER, 6, text="Confidential — page 2", page=1),
])


async def test_furniture_is_kept_as_disabled_by_role_chunks_and_toc_is_classified() -> None:
    node = ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=0)
    )
    chunks = (await node.run(ChunkerConsumes(ir=ROLE_IR))).chunks

    by_role: dict[ChunkRole, list] = {}
    for chunk in chunks:
        by_role.setdefault(chunk.role, []).append(chunk)

    # 1. Every structural role reached a chunk — nothing was dropped on ingest (reversible).
    assert set(by_role) == {ChunkRole.BODY, ChunkRole.HEADER_FOOTER, ChunkRole.TOC}

    # 2. The ToC section (heading + its list-like body) is classified from the heading title.
    toc_blocks = {b for c in by_role[ChunkRole.TOC] for b in c.block_ids}
    assert {"toc_h", "toc_a", "toc_b"} <= toc_blocks

    # 3. Header/footer furniture is kept, grouped per page (one chunk per page's furniture).
    hf_pages = sorted(c.page_start for c in by_role[ChunkRole.HEADER_FOOTER])
    assert hf_pages == [0, 1]
    assert all("Confidential" in c.text for c in by_role[ChunkRole.HEADER_FOOTER])

    # 4. Body keeps its role; furniture is disabled-by-role, body is enabled — the single policy.
    assert any("felines" in c.text for c in by_role[ChunkRole.BODY])
    assert all(role_default_enabled(c.role) for c in by_role[ChunkRole.BODY])
    assert not any(role_default_enabled(c.role) for c in by_role[ChunkRole.TOC])
    assert not any(role_default_enabled(c.role) for c in by_role[ChunkRole.HEADER_FOOTER])

    # 5. Furniture is appended AFTER the body — body chunks keep contiguous leading ordinals, so a
    #    method's neighbour/window logic over body is unaffected, and ordinals stay stable UUIDs.
    last_body = max(c.ordinal for c in by_role[ChunkRole.BODY])
    assert all(c.ordinal > last_body for c in by_role[ChunkRole.HEADER_FOOTER] + by_role[ChunkRole.TOC])
    assert [c.chunk_id for c in chunks] == [f"roles#c{c.ordinal}" for c in chunks]


def test_toc_matching_is_conservative_full_title_only() -> None:
    # A section whose title merely CONTAINS a ToC word must NOT be misread as scaffolding.
    ir = DocumentIR(doc_id="notoc", source_hash="h", n_pages=1, blocks=[
        _blk("h", BlockType.HEADING, 0, text="Table of contributions", level=1),
        _blk("p", BlockType.PARAGRAPH, 1, text="Real body content here.", parent="h"),
    ])
    passages = PassageProjector.project(ir, BaseChunkerConfig())
    assert all(p.role == ChunkRole.BODY for p in passages)


async def test_structure_aware_respects_sections_and_splits_oversized_paragraph() -> None:
    node = ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=120, max_tokens=200, min_tokens=10)
    )
    out = await node.run(ChunkerConsumes(ir=IR))
    chunks = out.chunks
    assert len(chunks) >= 3

    intro = [c for c in chunks if c.heading_path == ["Introduction"]]
    results = [c for c in chunks if c.heading_path == ["Results"]]
    assert intro and results
    assert all(c.token_count <= 200 for c in chunks)  # hard cap respected (LONG was split)
    assert any("ginger cat" in c.text for c in intro)  # figure meaning inside the flow
    assert chunks == sorted(chunks, key=lambda c: c.ordinal)
    assert all(c.chunk_id == f"doc1#c{c.ordinal}" for c in chunks)
    assert results[0].page_start == 1
    assert "| Metric | Value |" in results[0].text


TINY_SECTION = (
    "This short section describes a minor topic in only a couple of plain sentences, "
    "each kept deliberately small so the whole section stays well under the minimum."
)
BULK = " ".join(f"Bulk sentence {i} elaborates at length on the single dense section." for i in range(30))


def _many_tiny_sections_ir() -> DocumentIR:
    """An IR of 12 sub-min_tokens sections followed by one large standalone section."""
    blocks: list[Block] = []
    order = 0
    for index in range(12):
        blocks.append(_blk(f"h{index}", BlockType.HEADING, order, text=f"Section {index}", level=1))
        order += 1
        blocks.append(_blk(f"p{index}", BlockType.PARAGRAPH, order, text=TINY_SECTION, parent=f"h{index}"))
        order += 1
    blocks.append(_blk("hbulk", BlockType.HEADING, order, text="Bulk", level=1))
    blocks.append(_blk("pbulk", BlockType.PARAGRAPH, order + 1, text=BULK, parent="hbulk"))
    return DocumentIR(doc_id="tiny", source_hash="h", n_pages=1, blocks=blocks)


async def test_structure_aware_coalesces_consecutive_tiny_sections_toward_target() -> None:
    ir = _many_tiny_sections_ir()
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    node = ChunkerStructureAwareNode(id="c", config=config)
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks

    # 1. The 12 tiny sections no longer become 12 chunks — they coalesce far below one-per-section.
    assert 2 <= len(chunks) <= 5, [(c.heading_path, c.token_count) for c in chunks]

    # 2. Coalescing crosses section boundaries: some chunk unions blocks from >= 2 tiny sections,
    #    and it has grown past min_tokens (trending toward the target, not a lone fragment).
    tiny_ids = {f"h{i}" for i in range(12)} | {f"p{i}" for i in range(12)}
    coalesced = [c for c in chunks if len({b for b in c.block_ids if b in tiny_ids}) >= 2]
    assert coalesced
    assert any(c.token_count > config.min_tokens for c in coalesced)

    # 3. heading_path stays HONEST — the twelve sections are unrelated level-1 siblings, so their
    #    common ancestry is empty; a coalesced chunk must not claim to live under any one of them.
    assert chunks[0].heading_path == []

    # 4. The large section still stands ALONE in its own chunk — no neighbour glued onto it.
    bulk = [c for c in chunks if "pbulk" in c.block_ids]
    assert len(bulk) == 1
    assert bulk[0].block_ids == ["pbulk"]
    assert bulk[0].heading_path == ["Bulk"]
    assert bulk[0].token_count > config.target_tokens

    # 5. Merging never breaches the hard cap.
    assert all(c.token_count <= config.max_tokens for c in chunks)


async def test_structure_aware_real_section_does_not_absorb_a_following_fragment() -> None:
    # A real section (min <= x < target) directly followed by a tiny one: the fragment must NOT
    # glue onto the real section — a fragment-born run is the only run allowed to absorb.
    real_body = " ".join(f"Sentence {i} keeps this section comfortably above the minimum." for i in range(12))
    ir = DocumentIR(doc_id="mix", source_hash="h", n_pages=1, blocks=[
        _blk("hr", BlockType.HEADING, 0, text="Real", level=1),
        _blk("pr", BlockType.PARAGRAPH, 1, text=real_body, parent="hr"),
        _blk("ht", BlockType.HEADING, 2, text="Tiny", level=1),
        _blk("pt", BlockType.PARAGRAPH, 3, text="A tiny trailing note.", parent="ht"),
    ])
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    chunks = (await ChunkerStructureAwareNode(id="c", config=config).run(ChunkerConsumes(ir=ir))).chunks

    real = [c for c in chunks if "pr" in c.block_ids]
    tiny = [c for c in chunks if "pt" in c.block_ids]
    assert len(real) == 1 and len(tiny) == 1
    assert real[0].chunk_id != tiny[0].chunk_id           # the fragment stayed OUT of the real section
    assert "pt" not in real[0].block_ids
    assert config.min_tokens <= real[0].token_count       # the real section really was above min
    assert real[0].heading_path == ["Real"]               # single-section chunk keeps its exact path


async def test_structure_aware_coalesced_nested_sections_report_the_shared_ancestor() -> None:
    # Two tiny SUBSECTIONS under a common chapter coalesce; their common heading_path prefix is
    # the shared chapter, not empty and not a single subsection.
    ir = DocumentIR(doc_id="nest", source_hash="h", n_pages=1, blocks=[
        _blk("chap", BlockType.HEADING, 0, text="Chapter", level=1),
        _blk("sa", BlockType.HEADING, 1, text="Alpha", level=2, parent="chap"),
        _blk("pa", BlockType.PARAGRAPH, 2, text="A tiny note under alpha.", parent="sa"),
        _blk("sb", BlockType.HEADING, 3, text="Beta", level=2, parent="chap"),
        _blk("pb", BlockType.PARAGRAPH, 4, text="A tiny note under beta.", parent="sb"),
    ])
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    chunks = (await ChunkerStructureAwareNode(id="c", config=config).run(ChunkerConsumes(ir=ir))).chunks

    assert len(chunks) == 1                                # everything is tiny → one coalesced chunk
    assert {"pa", "pb"} <= set(chunks[0].block_ids)        # both subsections merged across the boundary
    assert chunks[0].heading_path == ["Chapter"]           # the shared ancestor, not [] nor a subsection


async def test_fixed_size_windows_with_repeated_overlap() -> None:
    node = ChunkerFixedSizeNode(id="c", config=ChunkerFixedSizeConfig(chunk_tokens=80, overlap_tokens=20))
    out = await node.run(ChunkerConsumes(ir=IR))
    windows = out.chunks
    assert len(windows) >= 3
    assert all(c.token_count <= 80 + 25 for c in windows)  # joins add a few tokens
    overlapped = any(
        windows[i].text.split("\n\n")[-1] in windows[i + 1].text for i in range(len(windows) - 1)
    )
    assert overlapped  # some tail passage repeated at the next window's start


def test_fixed_size_rejects_overlap_greater_or_equal_to_window() -> None:
    try:
        ChunkerFixedSizeConfig(chunk_tokens=100, overlap_tokens=100)
        raise AssertionError("overlap >= window not rejected")
    except ValueError:
        pass


class FakeSemantic(ChunkerSemanticNode):
    KIND = "test_chunk_stage_fake_semantic"
    NAME = "F"
    SUMMARY = "t"

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        # topic A = cats -> [1,0]; topic B = finance -> [0,1]
        return [[1.0, 0.0] if "cat" in t.lower() else [0.0, 1.0] for t in texts]


async def test_semantic_cuts_at_the_topic_shift() -> None:
    topics = DocumentIR(doc_id="d2", source_hash="h", n_pages=1, blocks=[
        _blk("a1", BlockType.PARAGRAPH, 0, text="Cats purr. Cats sleep a lot. A cat hunts mice."),
        _blk("b1", BlockType.PARAGRAPH, 1, text="Markets fell today. Inflation rose sharply. Bonds dropped."),
    ])
    node = FakeSemantic(id="c", config=ChunkerSemanticConfig(
        base_url="http://fake", model="fake", buffer_size=0, breakpoint_percentile=80.0,
        min_tokens=0, max_tokens=500))
    out = await node.run(ChunkerConsumes(ir=topics))
    chunks = out.chunks
    assert len(chunks) == 2, [c.text for c in chunks]
    assert "cat" in chunks[0].text.lower()
    assert "Markets" in chunks[1].text
    assert chunks[0].block_ids == ["a1"]
    assert chunks[1].block_ids == ["b1"]


def test_family_registration_and_describe_expose_the_ui_contract() -> None:
    kinds = NodeRegistry.kinds("chunker")
    assert {"structure_aware", "fixed_size", "semantic"} <= set(kinds)
    described = ChunkerStructureAwareNode.describe()
    for key in ("target_tokens", "overlap_tokens", "hard_section_boundaries", "figures_atomic", "tokenizer_encoding"):
        assert key in described.config_schema["properties"], key
    assert [(s.name, s.artefact_type) for s in described.consumes] == [("ir", "DocumentIR")]
    assert [(s.name, s.artefact_type) for s in described.produces] == [("chunks", "list[Chunk]")]


async def test_chunk_stage_blob_builds_validates_and_runs() -> None:
    blob = {
        "node_type": "group", "id": "chunk_stage",
        "nodes": [{"node_type": "action", "id": "chunk", "family": "chunker",
                   "kind": "structure_aware", "config": {"target_tokens": 256, "overlap_tokens": 32}}],
        "bindings": {"chunk": {"ir": {"source": "run", "field_name": "ir"}}},
    }
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    output, _record = await FlowEngine().execute(group, {"ir": IR})
    assert output.chunks
    # The tiny Introduction and the tiny Results heading/table are both sub-min_tokens and coalesce
    # across the boundary; their common ancestry is empty, so the first chunk honestly reports [].
    assert "h1" in output.chunks[0].block_ids
    assert output.chunks[0].heading_path == []


def test_f1_cyclic_parent_chain_does_not_hang_the_projection() -> None:
    cyclic = DocumentIR(doc_id="d3", source_hash="h", n_pages=1, blocks=[
        _blk("hx", BlockType.HEADING, 0, text="A", level=1, parent="hy"),
        _blk("hy", BlockType.HEADING, 1, text="B", level=2, parent="hx"),
        _blk("px", BlockType.PARAGRAPH, 2, text="Text.", parent="hx"),
    ])
    assert len(PassageProjector.project(cyclic, BaseChunkerConfig())) == 3


async def test_f2_oversized_atomic_table_stands_alone_over_both_methods() -> None:
    bigcells = [[f"metric {i}", f"value number {i}", f"comment about metric {i}"] for i in range(30)]
    big = DocumentIR(doc_id="d4", source_hash="h", n_pages=1, blocks=[
        _blk("q1", BlockType.PARAGRAPH, 0, text="Small intro sentence here."),
        _blk("q2", BlockType.PARAGRAPH, 1, text="Another small sentence follows."),
        _blk("tbig", BlockType.TABLE, 2, table=TableData(cells=bigcells, n_rows=30, n_cols=3, has_header=False)),
        _blk("q3", BlockType.PARAGRAPH, 3, text="A closing sentence."),
    ])
    for node in (
        ChunkerFixedSizeNode(id="c", config=ChunkerFixedSizeConfig(chunk_tokens=40, overlap_tokens=15)),
        ChunkerStructureAwareNode(id="c", config=ChunkerStructureAwareConfig(
            target_tokens=40, max_tokens=60, min_tokens=0, overlap_tokens=15)),
    ):
        out = await node.run(ChunkerConsumes(ir=big))
        table_chunks = [c for c in out.chunks if "tbig" in c.block_ids]
        assert len(table_chunks) == 1
        assert table_chunks[0].block_ids == ["tbig"]


async def test_f4_boundaryless_run_on_is_hard_cut() -> None:
    runon = DocumentIR(doc_id="d5", source_hash="h", n_pages=1, blocks=[
        _blk("r1", BlockType.PARAGRAPH, 0, text="mot " * 400)])
    out = await ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=60, max_tokens=80, min_tokens=0)
    ).run(ChunkerConsumes(ir=runon))
    assert out.chunks
    assert all(c.token_count <= 85 for c in out.chunks)


def test_figure_text_is_wrapped_in_an_explicit_image_marker() -> None:
    marked = DocumentIR(doc_id="d7", source_hash="h", n_pages=1, blocks=[
        _blk("fchart", BlockType.FIGURE, 0, text="Figure 2: quarterly revenue",
             figure=FigureEnrichment(kind=FigureKind.CHART, description="Revenue climbs each quarter.",
                                     ocr_text="Q1 100 Q2 140")),
        _blk("fdeco", BlockType.FIGURE, 1, figure=FigureEnrichment(kind=FigureKind.DECORATIVE)),
    ])
    passages = PassageProjector.project(marked, BaseChunkerConfig())
    assert [p.block_ids[0] for p in passages] == ["fchart"]   # decorative figure drops out

    text = passages[0].text
    lines = text.splitlines()
    # 1. Leading marker carries the figure kind and the native caption text.
    assert lines[0] == "[Image: chart] Figure 2: quarterly revenue"
    # 2. VLM description follows, framed as image-derived by the marker above.
    assert "Revenue climbs each quarter." in lines
    # 3. OCR text is present but labelled distinctly, never mistaken for the description.
    assert "[OCR] Q1 100 Q2 140" in lines
    # 4. Description and OCR stay verbatim in the text → still retrieval-friendly.
    assert "Revenue climbs each quarter." in text and "Q1 100 Q2 140" in text
    # 5. No chart-to-data extraction on this figure → no [Data] block.
    assert "[Data]" not in text


def test_figure_chart_to_data_renders_a_marked_markdown_table() -> None:
    charted = DocumentIR(doc_id="d8", source_hash="h", n_pages=1, blocks=[
        _blk("frev", BlockType.FIGURE, 0, text="Figure 1: Quarterly revenue by quarter, 2025.",
             figure=FigureEnrichment(
                 kind=FigureKind.CHART, description="Revenue rises across the year.",
                 data_table=[["Quarter", "Value"], ["Q1", "100"], ["Q2", "140"], ["Q4", "180"]])),
    ])
    text = PassageProjector.project(charted, BaseChunkerConfig())[0].text

    # 1. The extracted grid is appended under a distinct [Data] marker, after the description.
    assert "[Data]" in text
    assert text.index("Revenue rises across the year.") < text.index("[Data]")
    # 2. First grid row is the markdown header; the data rows follow verbatim.
    lines = text.splitlines()
    assert "| Quarter | Value |" in lines
    assert "| --- | --- |" in lines
    assert "| Q1 | 100 |" in lines
    assert "| Q4 | 180 |" in lines


def test_figure_with_only_a_data_table_still_produces_a_marked_chunk() -> None:
    data_only = DocumentIR(doc_id="d9", source_hash="h", n_pages=1, blocks=[
        _blk("fdata", BlockType.FIGURE, 0,
             figure=FigureEnrichment(kind=FigureKind.CHART,
                                     data_table=[["A", "B"], ["1", "2"]])),
    ])
    passages = PassageProjector.project(data_only, BaseChunkerConfig())
    assert len(passages) == 1                       # a data-only figure is NOT dropped
    text = passages[0].text
    assert text.startswith("[Image: chart]")        # marker still present
    assert "[Data]" in text
    assert "| A | B |" in text.splitlines()


def test_figure_with_empty_data_table_emits_no_data_block() -> None:
    empty = DocumentIR(doc_id="d10", source_hash="h", n_pages=1, blocks=[
        _blk("fempty", BlockType.FIGURE, 0, text="Figure 3: a photo",
             figure=FigureEnrichment(kind=FigureKind.PHOTO, description="A landscape.", data_table=[])),
    ])
    text = PassageProjector.project(empty, BaseChunkerConfig())[0].text
    assert "[Data]" not in text                      # empty grid contributes nothing
    assert "A landscape." in text


def test_figure_data_table_cells_are_sanitized() -> None:
    dirty = DocumentIR(doc_id="d11", source_hash="h", n_pages=1, blocks=[
        _blk("fdirty", BlockType.FIGURE, 0,
             figure=FigureEnrichment(kind=FigureKind.CHART,
                                     data_table=[["Series", "Note"], ["A | B", "line1\nline2"]])),
    ])
    text = PassageProjector.project(dirty, BaseChunkerConfig())[0].text
    lines = text.splitlines()
    # 1. A pipe inside a cell is escaped, not a phantom column separator.
    assert "| A \\| B | line1 line2 |" in lines
    # 2. The newline is flattened so the logical row stays on one markdown line.
    assert "line1\nline2" not in text
    # 3. The header separator still lands right after the header row (2 columns).
    assert lines[lines.index("| Series | Note |") + 1] == "| --- | --- |"


def test_f5_docling_style_caption_fuses_into_the_figure_unit() -> None:
    capir = DocumentIR(doc_id="d6", source_hash="h", n_pages=1, blocks=[
        _blk("cap1", BlockType.CAPTION, 0, text="Figure 1: revenue by quarter"),
        _blk("figx", BlockType.FIGURE, 1, figure=FigureEnrichment(description="A bar chart of revenue.", ocr_text="Q1 Q2")),
        _blk("pz", BlockType.PARAGRAPH, 2, text="Trailing text."),
    ])
    passages = PassageProjector.project(capir, BaseChunkerConfig())
    assert [p.block_ids for p in passages] == [["cap1", "figx"], ["pz"]]
    fused = passages[0]
    assert fused.atomic
    assert "Figure 1: revenue by quarter" in fused.text
    assert "bar chart" in fused.text
