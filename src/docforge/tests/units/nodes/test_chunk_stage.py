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


def _blk(
    bid, btype, order, page=0, text=None, parent=None, level=None, table=None, figure=None
) -> Block:
    return Block(
        id=bid,
        block_type=btype,
        reading_order=order,
        parent_id=parent,
        level=level,
        provenance=Provenance(page=page, bbox=(0.1, 0.1, 0.9, 0.9)),
        text=text,
        table=table,
        figure=figure,
    )


LONG = " ".join(f"Sentence number {i} talks about the same important subject." for i in range(40))
IR = DocumentIR(
    doc_id="doc1",
    source_hash="h",
    n_pages=2,
    blocks=[
        _blk("h1", BlockType.HEADING, 0, text="Introduction", level=1),
        _blk(
            "p1",
            BlockType.PARAGRAPH,
            1,
            text="Cats are small felines. They purr loudly.",
            parent="h1",
        ),
        _blk(
            "fig1",
            BlockType.FIGURE,
            2,
            text="Figure 1: a cat",
            parent="h1",
            figure=FigureEnrichment(description="A ginger cat sleeping.", ocr_text="CAT-01"),
        ),
        _blk("deco", BlockType.FIGURE, 3, parent="h1", figure=FigureEnrichment()),  # nothing to say
        _blk("hf", BlockType.HEADER_FOOTER, 4, text="Page 1 - Confidential"),  # excluded
        _blk("h2", BlockType.HEADING, 5, text="Results", level=1, page=1),
        _blk(
            "t1",
            BlockType.TABLE,
            6,
            parent="h2",
            page=1,
            table=TableData(
                cells=[["Metric", "Value"], ["Accuracy", "0.93"]],
                n_rows=2,
                n_cols=2,
                has_header=True,
            ),
        ),
        _blk("p2", BlockType.PARAGRAPH, 7, text=LONG, parent="h2", page=1),
    ],
)


def test_shared_projection_composition_rules() -> None:
    passages = PassageProjector.project(IR, BaseChunkerConfig())
    by_first_block = {passage.block_ids[0]: passage for passage in passages}
    # Header/footer is no longer dropped — it is projected as a HEADER_FOOTER-role passage.
    assert [ps.block_ids[0] for ps in passages] == ["h1", "p1", "fig1", "hf", "h2", "t1", "p2"]

    fig = by_first_block["fig1"]
    assert fig.atomic
    assert "[Image:" not in fig.text  # content-free image marker never leaks into searchable text
    assert fig.text.startswith("Figure 1: a cat")  # the native caption leads, verbatim
    assert "ginger cat" in fig.text
    assert "[OCR] CAT-01" in fig.text  # OCR labelled distinctly from the description
    assert "deco" not in by_first_block  # empty/decorative figure still drops out

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


ROLE_IR = DocumentIR(
    doc_id="roles",
    source_hash="h",
    n_pages=2,
    blocks=[
        _blk("toc_h", BlockType.HEADING, 0, text="Table of Contents", level=1),
        _blk("toc_a", BlockType.LIST_ITEM, 1, text="1. Introduction .......... 1", parent="toc_h"),
        _blk("toc_b", BlockType.LIST_ITEM, 2, text="2. Results .......... 4", parent="toc_h"),
        _blk("hf0", BlockType.HEADER_FOOTER, 3, text="Confidential — page 1"),
        _blk("intro_h", BlockType.HEADING, 4, text="Introduction", level=1, page=1),
        _blk(
            "intro_p",
            BlockType.PARAGRAPH,
            5,
            text="Cats are small felines. They purr loudly.",
            parent="intro_h",
            page=1,
        ),
        _blk("hf1", BlockType.HEADER_FOOTER, 6, text="Confidential — page 2", page=1),
    ],
)


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
    assert all(
        c.ordinal > last_body for c in by_role[ChunkRole.HEADER_FOOTER] + by_role[ChunkRole.TOC]
    )
    assert [c.chunk_id for c in chunks] == [f"roles#c{c.ordinal}" for c in chunks]


def test_toc_matching_is_conservative_full_title_only() -> None:
    # A section whose title merely CONTAINS a ToC word must NOT be misread as scaffolding.
    ir = DocumentIR(
        doc_id="notoc",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("h", BlockType.HEADING, 0, text="Table of contributions", level=1),
            _blk("p", BlockType.PARAGRAPH, 1, text="Real body content here.", parent="h"),
        ],
    )
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
BULK = " ".join(
    f"Bulk sentence {i} elaborates at length on the single dense section." for i in range(30)
)


def _many_tiny_sections_ir() -> DocumentIR:
    """An IR of 12 sub-min_tokens sections followed by one large standalone section."""
    blocks: list[Block] = []
    order = 0
    for index in range(12):
        blocks.append(_blk(f"h{index}", BlockType.HEADING, order, text=f"Section {index}", level=1))
        order += 1
        blocks.append(
            _blk(f"p{index}", BlockType.PARAGRAPH, order, text=TINY_SECTION, parent=f"h{index}")
        )
        order += 1
    blocks.append(_blk("hbulk", BlockType.HEADING, order, text="Bulk", level=1))
    blocks.append(_blk("pbulk", BlockType.PARAGRAPH, order + 1, text=BULK, parent="hbulk"))
    return DocumentIR(doc_id="tiny", source_hash="h", n_pages=1, blocks=blocks)


async def test_structure_aware_keeps_short_titled_sections_as_their_own_chunks() -> None:
    ir = _many_tiny_sections_ir()
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    node = ChunkerStructureAwareNode(id="c", config=config)
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks

    # 1. Each short titled section is a citable unit → it stays its OWN chunk (coalescing never
    #    crosses a section TITLE), so the 12 tiny sections yield 12 body chunks plus the bulk one.
    body = [c for c in chunks if c.role is ChunkRole.BODY]
    assert len(body) == 13, [(c.heading_path, c.token_count) for c in body]

    # 2. Every tiny section keeps its OWN heading_path — short, yet standalone and citable — and
    #    holds only its own blocks (no neighbour section glued onto it).
    for index in range(12):
        section = [c for c in body if c.heading_path == [f"Section {index}"]]
        assert len(section) == 1, [c.heading_path for c in body]
        chunk = section[0]
        assert f"h{index}" in chunk.block_ids and f"p{index}" in chunk.block_ids
        assert chunk.token_count < config.min_tokens  # below the fragment threshold, yet standalone
        others = {f"p{j}" for j in range(12) if j != index}
        assert not (others & set(chunk.block_ids))

    # 3. The large section still stands ALONE in its own chunk — no neighbour glued onto it. Its
    #    OWN heading ("Bulk") is carried as provenance (block id only, no repeated title in body),
    #    so the chunk spans the heading + its paragraph but no other section's blocks.
    bulk = [c for c in chunks if "pbulk" in c.block_ids]
    assert len(bulk) == 1
    assert bulk[0].block_ids == ["hbulk", "pbulk"]
    assert bulk[0].heading_path == ["Bulk"]
    assert bulk[0].token_count > config.target_tokens

    # 4. Nothing breaches the hard cap.
    assert all(c.token_count <= config.max_tokens for c in chunks)


async def test_structure_aware_still_coalesces_heading_less_fragments() -> None:
    """Genuinely heading-less micro-fragments (structural dividers with no title text) still
    coalesce across boundaries toward the target — only TITLED sections are kept apart. A blank
    heading yields no citable breadcrumb, so its fragment is not a unit worth standing alone."""
    tiny = "A short heading-less fragment of only a handful of plain words here."
    ir = DocumentIR(
        doc_id="hless",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("hb1", BlockType.HEADING, 0, text="", level=1),  # blank divider, no title text
            _blk("pb1", BlockType.PARAGRAPH, 1, text=tiny, parent="hb1"),
            _blk("hb2", BlockType.HEADING, 2, text="", level=1),
            _blk("pb2", BlockType.PARAGRAPH, 3, text=tiny, parent="hb2"),
            _blk("hb3", BlockType.HEADING, 4, text="", level=1),
            _blk("pb3", BlockType.PARAGRAPH, 5, text=tiny, parent="hb3"),
        ],
    )
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    chunks = (
        await ChunkerStructureAwareNode(id="c", config=config).run(ChunkerConsumes(ir=ir))
    ).chunks

    body = [c for c in chunks if c.role is ChunkRole.BODY]
    # The three heading-less fragments (each below min_tokens) fold into a single chunk — they carry
    # no citable title, so keeping them apart would only make a swarm of tiny fragments.
    assert len(body) == 1, [(c.heading_path, c.block_ids) for c in body]
    assert {"pb1", "pb2", "pb3"} <= set(body[0].block_ids)
    assert body[0].heading_path == []  # unrelated blank sections → honest empty ancestry
    assert body[0].token_count <= config.max_tokens


async def test_structure_aware_real_section_does_not_absorb_a_following_fragment() -> None:
    # A real section (min <= x < target) directly followed by a tiny one: the fragment must NOT
    # glue onto the real section — a fragment-born run is the only run allowed to absorb.
    real_body = " ".join(
        f"Sentence {i} keeps this section comfortably above the minimum." for i in range(12)
    )
    ir = DocumentIR(
        doc_id="mix",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("hr", BlockType.HEADING, 0, text="Real", level=1),
            _blk("pr", BlockType.PARAGRAPH, 1, text=real_body, parent="hr"),
            _blk("ht", BlockType.HEADING, 2, text="Tiny", level=1),
            _blk("pt", BlockType.PARAGRAPH, 3, text="A tiny trailing note.", parent="ht"),
        ],
    )
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    chunks = (
        await ChunkerStructureAwareNode(id="c", config=config).run(ChunkerConsumes(ir=ir))
    ).chunks

    real = [c for c in chunks if "pr" in c.block_ids]
    tiny = [c for c in chunks if "pt" in c.block_ids]
    assert len(real) == 1 and len(tiny) == 1
    assert real[0].chunk_id != tiny[0].chunk_id  # the fragment stayed OUT of the real section
    assert "pt" not in real[0].block_ids
    assert config.min_tokens <= real[0].token_count  # the real section really was above min
    assert real[0].heading_path == ["Real"]  # single-section chunk keeps its exact path


async def test_structure_aware_keeps_short_titled_subsections_separate() -> None:
    # Two tiny SUBSECTIONS under a common chapter: each is a titled, citable unit, so they do NOT
    # coalesce — each stays its own chunk reporting its full Chapter › Subsection breadcrumb.
    ir = DocumentIR(
        doc_id="nest",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("chap", BlockType.HEADING, 0, text="Chapter", level=1),
            _blk("sa", BlockType.HEADING, 1, text="Alpha", level=2, parent="chap"),
            _blk("pa", BlockType.PARAGRAPH, 2, text="A tiny note under alpha.", parent="sa"),
            _blk("sb", BlockType.HEADING, 3, text="Beta", level=2, parent="chap"),
            _blk("pb", BlockType.PARAGRAPH, 4, text="A tiny note under beta.", parent="sb"),
        ],
    )
    config = ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=64)
    chunks = (
        await ChunkerStructureAwareNode(id="c", config=config).run(ChunkerConsumes(ir=ir))
    ).chunks

    body = [c for c in chunks if c.role is ChunkRole.BODY]
    assert len(body) == 2  # each titled subsection stays its own chunk, tiny though it is
    alpha = next(c for c in body if "pa" in c.block_ids)
    beta = next(c for c in body if "pb" in c.block_ids)
    assert alpha.heading_path == ["Chapter", "Alpha"]  # full breadcrumb, not just the shared ancestor
    assert beta.heading_path == ["Chapter", "Beta"]
    assert "pb" not in alpha.block_ids and "pa" not in beta.block_ids  # never glued together


async def test_fixed_size_windows_with_repeated_overlap() -> None:
    node = ChunkerFixedSizeNode(
        id="c", config=ChunkerFixedSizeConfig(chunk_tokens=80, overlap_tokens=20)
    )
    out = await node.run(ChunkerConsumes(ir=IR))
    windows = out.chunks
    assert len(windows) >= 3
    assert all(c.token_count <= 80 + 25 for c in windows)  # joins add a few tokens
    overlapped = any(
        windows[i].text.split("\n\n")[-1] in windows[i + 1].text for i in range(len(windows) - 1)
    )
    assert overlapped  # some tail passage repeated at the next window's start


def _one_big_section_ir() -> DocumentIR:
    """One section whose paragraphs overflow target_tokens, forcing SIZE cuts within the section."""
    blocks: list[Block] = [_blk("h", BlockType.HEADING, 0, text="Big Section", level=1)]
    for index in range(10):
        blocks.append(
            _blk(
                f"p{index}",
                BlockType.PARAGRAPH,
                index + 1,
                text=(
                    f"Paragraph {index} discusses subtopic number {index} at moderate length, "
                    "adding several extra words here to reach roughly thirty tokens of distinct "
                    f"content that belongs only to passage {index} of this one section."
                ),
                parent="h",
            )
        )
    return DocumentIR(doc_id="big", source_hash="h", n_pages=1, blocks=blocks)


async def test_structure_aware_size_split_overlaps_by_default_and_can_be_disabled() -> None:
    # A single section split by SIZE now overlaps by default (overlap_tokens=64), so a fact on the
    # cut survives in a chunk; overlap_tokens=0 restores the hard, no-repeat cut. A section-boundary
    # cut never overlaps, so documents whose sections fit the target are unaffected (tested elsewhere).
    ir = _one_big_section_ir()

    default_cfg = ChunkerStructureAwareConfig(target_tokens=120, max_tokens=400, min_tokens=0)
    default_chunks = (
        await ChunkerStructureAwareNode(id="c", config=default_cfg).run(ChunkerConsumes(ir=ir))
    ).chunks
    assert len(default_chunks) >= 2  # the section was size-split into several chunks

    def _tail_repeats(chunks: list) -> bool:
        return any(
            chunks[i].text.split("\n\n")[-1] in chunks[i + 1].text for i in range(len(chunks) - 1)
        )

    assert _tail_repeats(
        default_chunks
    )  # default overlap repeats a tail passage into the next chunk

    off_cfg = ChunkerStructureAwareConfig(
        target_tokens=120, max_tokens=400, min_tokens=0, overlap_tokens=0
    )
    off_chunks = (
        await ChunkerStructureAwareNode(id="c", config=off_cfg).run(ChunkerConsumes(ir=ir))
    ).chunks
    assert len(off_chunks) >= 2
    assert not _tail_repeats(off_chunks)  # overlap_tokens=0 repeats nothing


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
    topics = DocumentIR(
        doc_id="d2",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "a1", BlockType.PARAGRAPH, 0, text="Cats purr. Cats sleep a lot. A cat hunts mice."
            ),
            _blk(
                "b1",
                BlockType.PARAGRAPH,
                1,
                text="Markets fell today. Inflation rose sharply. Bonds dropped.",
            ),
        ],
    )
    node = FakeSemantic(
        id="c",
        config=ChunkerSemanticConfig(
            base_url="http://fake",
            model="fake",
            buffer_size=0,
            breakpoint_percentile=80.0,
            min_tokens=0,
            max_tokens=500,
        ),
    )
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
    for key in (
        "target_tokens",
        "overlap_tokens",
        "hard_section_boundaries",
        "figures_atomic",
        "tokenizer_encoding",
    ):
        assert key in described.config_schema["properties"], key
    assert [(s.name, s.artefact_type) for s in described.consumes] == [("ir", "DocumentIR")]
    assert [(s.name, s.artefact_type) for s in described.produces] == [("chunks", "list[Chunk]")]


async def test_chunk_stage_blob_builds_validates_and_runs() -> None:
    blob = {
        "node_type": "group",
        "id": "chunk_stage",
        "nodes": [
            {
                "node_type": "action",
                "id": "chunk",
                "family": "chunker",
                "kind": "structure_aware",
                "config": {"target_tokens": 256, "overlap_tokens": 32},
            }
        ],
        "bindings": {"chunk": {"ir": {"source": "run", "field_name": "ir"}}},
    }
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    output, _record = await FlowEngine().execute(group, {"ir": IR})
    assert output.chunks
    # Introduction and Results are each their OWN titled section — short though Introduction is — so
    # they no longer coalesce across the boundary; the first chunk cites Introduction precisely.
    assert "h1" in output.chunks[0].block_ids
    assert output.chunks[0].heading_path == ["Introduction"]


def test_f1_cyclic_parent_chain_does_not_hang_the_projection() -> None:
    cyclic = DocumentIR(
        doc_id="d3",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("hx", BlockType.HEADING, 0, text="A", level=1, parent="hy"),
            _blk("hy", BlockType.HEADING, 1, text="B", level=2, parent="hx"),
            _blk("px", BlockType.PARAGRAPH, 2, text="Text.", parent="hx"),
        ],
    )
    assert len(PassageProjector.project(cyclic, BaseChunkerConfig())) == 3


async def test_f2_oversized_atomic_table_stands_alone_over_both_methods() -> None:
    bigcells = [
        [f"metric {i}", f"value number {i}", f"comment about metric {i}"] for i in range(30)
    ]
    big = DocumentIR(
        doc_id="d4",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("q1", BlockType.PARAGRAPH, 0, text="Small intro sentence here."),
            _blk("q2", BlockType.PARAGRAPH, 1, text="Another small sentence follows."),
            _blk(
                "tbig",
                BlockType.TABLE,
                2,
                table=TableData(cells=bigcells, n_rows=30, n_cols=3, has_header=False),
            ),
            _blk("q3", BlockType.PARAGRAPH, 3, text="A closing sentence."),
        ],
    )
    for node in (
        ChunkerFixedSizeNode(
            id="c", config=ChunkerFixedSizeConfig(chunk_tokens=40, overlap_tokens=15)
        ),
        ChunkerStructureAwareNode(
            id="c",
            config=ChunkerStructureAwareConfig(
                target_tokens=40, max_tokens=60, min_tokens=0, overlap_tokens=15
            ),
        ),
    ):
        out = await node.run(ChunkerConsumes(ir=big))
        table_chunks = [c for c in out.chunks if "tbig" in c.block_ids]
        assert len(table_chunks) == 1
        assert table_chunks[0].block_ids == ["tbig"]


async def test_f4_boundaryless_run_on_is_hard_cut() -> None:
    runon = DocumentIR(
        doc_id="d5",
        source_hash="h",
        n_pages=1,
        blocks=[_blk("r1", BlockType.PARAGRAPH, 0, text="mot " * 400)],
    )
    out = await ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=60, max_tokens=80, min_tokens=0)
    ).run(ChunkerConsumes(ir=runon))
    assert out.chunks
    assert all(c.token_count <= 85 for c in out.chunks)


def test_figure_text_keeps_content_but_drops_the_bare_image_marker() -> None:
    marked = DocumentIR(
        doc_id="d7",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "fchart",
                BlockType.FIGURE,
                0,
                text="Figure 2: quarterly revenue",
                figure=FigureEnrichment(
                    kind=FigureKind.CHART,
                    description="Revenue climbs each quarter.",
                    ocr_text="Q1 100 Q2 140",
                ),
            ),
            _blk("fdeco", BlockType.FIGURE, 1, figure=FigureEnrichment(kind=FigureKind.DECORATIVE)),
        ],
    )
    passages = PassageProjector.project(marked, BaseChunkerConfig())
    assert [p.block_ids[0] for p in passages] == ["fchart"]  # decorative figure drops out

    text = passages[0].text
    lines = text.splitlines()
    # 1. The content-free "[Image: <kind>]" marker is gone — it carried no searchable text and
    #    would otherwise let a bare "chart" query match a figure with no answer in it.
    assert "[Image:" not in text
    # 2. The native caption leads, verbatim.
    assert lines[0] == "Figure 2: quarterly revenue"
    # 3. VLM description follows.
    assert "Revenue climbs each quarter." in lines
    # 4. OCR text is present but labelled distinctly, never mistaken for the description.
    assert "[OCR] Q1 100 Q2 140" in lines
    # 5. Description and OCR stay verbatim in the text → still retrieval-friendly.
    assert "Revenue climbs each quarter." in text and "Q1 100 Q2 140" in text
    # 6. No chart-to-data extraction on this figure → no [Data] block.
    assert "[Data]" not in text


async def test_short_titled_sibling_sections_each_stay_their_own_chunk() -> None:
    """A glossary-style doc of tiny sibling sections: each term is a citable unit, so it stays its
    OWN chunk with its own heading_path — no coalescing across titles, so term-precise retrieval is
    preserved (a query for one term resolves to exactly its chunk, not a merged blob of all terms)."""
    ir = DocumentIR(
        doc_id="gloss",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("hz", BlockType.HEADING, 0, text="Zero Trust", level=1),
            _blk(
                "dz", BlockType.PARAGRAPH, 1, text="A model where nothing is trusted.", parent="hz"
            ),
            _blk("hm", BlockType.HEADING, 2, text="Mesh Registry", level=1),
            _blk(
                "dm", BlockType.PARAGRAPH, 3, text="A directory of service endpoints.", parent="hm"
            ),
            _blk("hi", BlockType.HEADING, 4, text="Idempotency Key", level=1),
            _blk("di", BlockType.PARAGRAPH, 5, text="A token making retries safe.", parent="hi"),
        ],
    )
    node = ChunkerStructureAwareNode(id="c", config=ChunkerStructureAwareConfig())
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks
    body = [c for c in chunks if c.role is ChunkRole.BODY]
    assert len(body) == 3, "each tiny sibling term stays its own citable chunk (no swarm-into-blob)"
    for term, para in (("Zero Trust", "dz"), ("Mesh Registry", "dm"), ("Idempotency Key", "di")):
        chunk = next(c for c in body if para in c.block_ids)
        assert chunk.heading_path == [term]  # each term citable by its own breadcrumb


async def test_single_section_chunk_does_not_duplicate_its_heading_inline() -> None:
    """A single-section chunk's heading is already in its heading_path (the breadcrumb renders it),
    so it must NOT be duplicated into the body."""
    ir = DocumentIR(
        doc_id="one",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("h", BlockType.HEADING, 0, text="Overview", level=1),
            _blk(
                "p",
                BlockType.PARAGRAPH,
                1,
                text=" ".join(
                    f"sentence {i} with enough words to be a real section" for i in range(12)
                ),
                parent="h",
            ),
        ],
    )
    node = ChunkerStructureAwareNode(id="c", config=ChunkerStructureAwareConfig())
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks
    assert chunks[0].heading_path == ["Overview"]  # section named by the breadcrumb
    assert not chunks[0].text.startswith("Overview"), "heading must not be duplicated into the body"


def test_figure_with_a_crop_but_no_caption_contributes_no_passage() -> None:
    """A detected figure carrying a CROP but no caption/enrichment (the out-of-box, enrich-off case)
    contributes NO searchable text: a bare "[Image: <kind>]" marker with nothing behind it would
    become a content-free chunk that ranks as a top hit and mis-cites a real filename. The crop still
    lives on the IR block (reachable via the document view); it must not seed a placeholder passage."""
    ir = DocumentIR(
        doc_id="dcrop",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("h1", BlockType.HEADING, 0, text="System Architecture", level=1),
            _blk(
                "figcrop",
                BlockType.FIGURE,
                1,
                parent="h1",
                figure=FigureEnrichment(kind=FigureKind.DIAGRAM, crop=b"\x89PNG-bytes"),
            ),
        ],
    )
    passages = PassageProjector.project(ir, BaseChunkerConfig())
    assert not [p for p in passages if "figcrop" in p.block_ids], (
        "a crop-only figure (no caption/OCR/description) must not seed a placeholder passage"
    )


def test_render_figure_emits_nothing_for_a_bare_crop_but_keeps_enriched_figures() -> None:
    """render_figure returns None for a content-free figure (crop only / nothing) — never a bare
    "[Image: <kind>]" marker — but ANY of a caption, native text, description or OCR keeps its real
    content, unmarked by the content-free image label."""
    from shared_libs.pipelines.ingest.nodes.chunk.base.helpers import ChunkerHelpers

    crop_only = FigureEnrichment(kind=FigureKind.PHOTO, crop=b"\x89PNG")
    assert ChunkerHelpers.render_figure(crop_only, caption=None, native_text=None) is None
    assert ChunkerHelpers.render_figure(FigureEnrichment(kind=FigureKind.PHOTO), None, None) is None
    # A caption keeps the figure — it carries real, searchable prose about the image — but the
    # content-free "[Image: photo]" marker is NOT prepended to it.
    with_caption = ChunkerHelpers.render_figure(crop_only, caption="A ginger cat", native_text=None)
    assert with_caption == "A ginger cat"
    assert "[Image:" not in with_caption
    # OCR text alone is enough content to keep the figure, still with no bare image marker.
    ocr = FigureEnrichment(kind=FigureKind.PHOTO, crop=b"\x89PNG", ocr_text="TOTAL 35.72")
    rendered = ChunkerHelpers.render_figure(ocr, caption=None, native_text=None)
    assert rendered is not None and rendered == "[OCR] TOTAL 35.72" and "[Image:" not in rendered


def test_caption_survives_when_its_table_is_empty() -> None:
    """A caption whose owning table produces nothing (no cells) must not vanish — its text is kept
    as its own passage, with both the caption and the table block in provenance."""
    ir = DocumentIR(
        doc_id="dcap",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "temp",
                BlockType.TABLE,
                0,
                table=TableData(cells=[], n_rows=0, n_cols=0, has_header=False),
            ),
            _blk("cap", BlockType.CAPTION, 1, text="Table 1: Q3 revenue by region"),
        ],
    )
    passages = PassageProjector.project(ir, BaseChunkerConfig())
    texts = [p.text for p in passages]
    assert "Table 1: Q3 revenue by region" in texts, texts
    caption_passage = next(p for p in passages if p.text == "Table 1: Q3 revenue by region")
    assert "cap" in caption_passage.block_ids and "temp" in caption_passage.block_ids


def test_figure_chart_to_data_renders_a_marked_markdown_table() -> None:
    charted = DocumentIR(
        doc_id="d8",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "frev",
                BlockType.FIGURE,
                0,
                text="Figure 1: Quarterly revenue by quarter, 2025.",
                figure=FigureEnrichment(
                    kind=FigureKind.CHART,
                    description="Revenue rises across the year.",
                    data_table=[["Quarter", "Value"], ["Q1", "100"], ["Q2", "140"], ["Q4", "180"]],
                ),
            ),
        ],
    )
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
    data_only = DocumentIR(
        doc_id="d9",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "fdata",
                BlockType.FIGURE,
                0,
                figure=FigureEnrichment(kind=FigureKind.CHART, data_table=[["A", "B"], ["1", "2"]]),
            ),
        ],
    )
    passages = PassageProjector.project(data_only, BaseChunkerConfig())
    assert len(passages) == 1  # a data-only figure is NOT dropped
    text = passages[0].text
    assert "[Image:" not in text  # no content-free marker, even with nothing else to lead with
    assert text.startswith("[Data]")  # the extracted grid is the figure's only content
    assert "| A | B |" in text.splitlines()


def test_figure_with_empty_data_table_emits_no_data_block() -> None:
    empty = DocumentIR(
        doc_id="d10",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "fempty",
                BlockType.FIGURE,
                0,
                text="Figure 3: a photo",
                figure=FigureEnrichment(
                    kind=FigureKind.PHOTO, description="A landscape.", data_table=[]
                ),
            ),
        ],
    )
    text = PassageProjector.project(empty, BaseChunkerConfig())[0].text
    assert "[Data]" not in text  # empty grid contributes nothing
    assert "A landscape." in text


def test_figure_data_table_cells_are_sanitized() -> None:
    dirty = DocumentIR(
        doc_id="d11",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk(
                "fdirty",
                BlockType.FIGURE,
                0,
                figure=FigureEnrichment(
                    kind=FigureKind.CHART,
                    data_table=[["Series", "Note"], ["A | B", "line1\nline2"]],
                ),
            ),
        ],
    )
    text = PassageProjector.project(dirty, BaseChunkerConfig())[0].text
    lines = text.splitlines()
    # 1. A pipe inside a cell is escaped, not a phantom column separator.
    assert "| A \\| B | line1 line2 |" in lines
    # 2. The newline is flattened so the logical row stays on one markdown line.
    assert "line1\nline2" not in text
    # 3. The header separator still lands right after the header row (2 columns).
    assert lines[lines.index("| Series | Note |") + 1] == "| --- | --- |"


def test_f5_docling_style_caption_fuses_into_the_figure_unit() -> None:
    capir = DocumentIR(
        doc_id="d6",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("cap1", BlockType.CAPTION, 0, text="Figure 1: revenue by quarter"),
            _blk(
                "figx",
                BlockType.FIGURE,
                1,
                figure=FigureEnrichment(description="A bar chart of revenue.", ocr_text="Q1 Q2"),
            ),
            _blk("pz", BlockType.PARAGRAPH, 2, text="Trailing text."),
        ],
    )
    passages = PassageProjector.project(capir, BaseChunkerConfig())
    assert [p.block_ids for p in passages] == [["cap1", "figx"], ["pz"]]
    fused = passages[0]
    assert fused.atomic
    assert "Figure 1: revenue by quarter" in fused.text
    assert "bar chart" in fused.text


# ============================ FIX 2 — repeated-boilerplate detection ============================

_BOILER = "Objective one grow. Objective two scale. Objective three win."


def _deck_ir(pages: int = 6) -> DocumentIR:
    """A slide deck: each page has a unique body PLUS the SAME objectives block (boilerplate)."""
    blocks: list[Block] = []
    order = 0
    for page in range(1, pages + 1):
        blocks.append(
            _blk(f"h{page}", BlockType.HEADING, order, page=page, text=f"Slide {page}", level=1)
        )
        order += 1
        blocks.append(
            _blk(
                f"body{page}",
                BlockType.PARAGRAPH,
                order,
                page=page,
                parent=f"h{page}",
                text=f"Unique paragraph {page} discussing a genuinely distinct topic here.",
            )
        )
        order += 1
        blocks.append(
            _blk(
                f"obj{page}", BlockType.LIST_ITEM, order, page=page, parent=f"h{page}", text=_BOILER
            )
        )
        order += 1
    return DocumentIR(doc_id="deck", source_hash="h", n_pages=pages, blocks=blocks)


def test_fix2_text_repeated_across_pages_is_classified_boilerplate() -> None:
    # The objectives block recurs on 6 distinct pages (>= default min_pages=3) → BOILERPLATE, and
    # BOILERPLATE is default-disabled (never embedded); the per-page unique bodies stay BODY.
    passages = PassageProjector.project(_deck_ir(6), BaseChunkerConfig())
    boiler = [p for p in passages if p.role is ChunkRole.BOILERPLATE]
    assert len(boiler) == 6  # one per repeating occurrence
    assert all(p.text == _BOILER for p in boiler)
    assert not role_default_enabled(ChunkRole.BOILERPLATE)  # disabled-by-role, like header/footer
    assert all(p.role is ChunkRole.BODY for p in passages if p.block_ids[0].startswith("body"))


async def test_fix2_boilerplate_is_removed_from_body_chunks_and_kept_as_disabled_chunks() -> None:
    # The behavioral acceptance: the repeated block must NOT leak into any body chunk's text, and
    # must survive only as its own BOILERPLATE, default-disabled chunk(s).
    node = ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=0)
    )
    chunks = (await node.run(ChunkerConsumes(ir=_deck_ir(6)))).chunks

    body = [c for c in chunks if c.role is ChunkRole.BODY]
    boiler = [c for c in chunks if c.role is ChunkRole.BOILERPLATE]
    assert body and boiler
    assert not any(_BOILER in c.text for c in body)  # the leak is gone from body chunks
    assert all(_BOILER in c.text for c in boiler)  # kept, verbatim, out of the body
    assert all(not role_default_enabled(c.role) for c in boiler)  # non-embedded by default


def test_fix2_repetition_within_a_single_page_stays_body() -> None:
    # The SAME text three times on ONE page is not cross-page repetition → it stays BODY.
    ir = DocumentIR(
        doc_id="one",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("a", BlockType.PARAGRAPH, 0, page=0, text=_BOILER),
            _blk("b", BlockType.PARAGRAPH, 1, page=0, text=_BOILER),
            _blk("c", BlockType.PARAGRAPH, 2, page=0, text=_BOILER),
        ],
    )
    passages = PassageProjector.project(ir, BaseChunkerConfig())
    assert all(p.role is ChunkRole.BODY for p in passages)  # distinct pages, not occurrences


def test_fix2_detection_is_configurable_off_and_by_threshold() -> None:
    ir = _deck_ir(4)  # repeats on 4 distinct pages
    # 1. Switch OFF → the config knob is actually read; nothing is boilerplate.
    off = PassageProjector.project(ir, BaseChunkerConfig(detect_repeated_boilerplate=False))
    assert all(p.role is ChunkRole.BODY for p in off)
    # 2. Threshold above the observed repetition (5 > 4) → not enough pages, stays body.
    high = PassageProjector.project(ir, BaseChunkerConfig(boilerplate_min_pages=5))
    assert all(p.role is ChunkRole.BODY for p in high)
    # 3. Threshold at the repetition count (4) → caught.
    at = PassageProjector.project(ir, BaseChunkerConfig(boilerplate_min_pages=4))
    assert any(p.role is ChunkRole.BOILERPLATE for p in at)


# ============================ FIX 3 — heading-only orphan passages ============================


async def test_fix3_orphan_heading_does_not_become_a_standalone_chunk() -> None:
    # A stray heading with no body of its own (nothing lives under it) must not be its own chunk;
    # it is folded FORWARD as the next section's breadcrumb, and its title is not lost.
    ir = DocumentIR(
        doc_id="orph",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("h1", BlockType.HEADING, 0, text="Real section", level=1),
            _blk(
                "p1",
                BlockType.PARAGRAPH,
                1,
                text="Body of the real section, several plain words here.",
                parent="h1",
            ),
            _blk(
                "stray", BlockType.HEADING, 2, text="Section: Contexte", level=1
            ),  # no body under it
            _blk("h2", BlockType.HEADING, 3, text="Next section", level=1),
            _blk(
                "p2",
                BlockType.PARAGRAPH,
                4,
                text="Body of the next section, also several plain words.",
                parent="h2",
            ),
        ],
    )
    node = ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=0)
    )
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks

    assert not any(c.text.strip() == "Section: Contexte" for c in chunks)  # never standalone
    assert any("Section: Contexte" in c.text for c in chunks)  # title preserved forward
    stray_chunk = next(c for c in chunks if "Section: Contexte" in c.text)
    assert (
        "stray" in stray_chunk.block_ids and "p2" in stray_chunk.block_ids
    )  # merged into next body


async def test_fix3_trailing_orphan_heading_merges_backward() -> None:
    # A trailing heading with nothing after it (e.g. before a content-less tail) merges BACKWARD
    # onto the previous chunk so its title survives rather than being dropped.
    ir = DocumentIR(
        doc_id="tail",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("h1", BlockType.HEADING, 0, text="Only section", level=1),
            _blk(
                "p1",
                BlockType.PARAGRAPH,
                1,
                text="The sole body paragraph of the document here.",
                parent="h1",
            ),
            _blk("tail", BlockType.HEADING, 2, text="Appendix", level=1),  # trailing, no body
        ],
    )
    node = ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=0)
    )
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks

    assert not any(c.text.strip() == "Appendix" for c in chunks)  # not a standalone chunk
    merged = next(c for c in chunks if "Appendix" in c.text)
    assert "p1" in merged.block_ids and "tail" in merged.block_ids  # folded backward


async def test_fix3_populated_section_heading_is_not_treated_as_orphan() -> None:
    # A heading that owns real content keeps packing with its body — no regression.
    ir = DocumentIR(
        doc_id="ok",
        source_hash="h",
        n_pages=1,
        blocks=[
            _blk("h1", BlockType.HEADING, 0, text="Populated", level=1),
            _blk(
                "p1",
                BlockType.PARAGRAPH,
                1,
                text="A comfortably sized body paragraph of real content.",
                parent="h1",
            ),
        ],
    )
    node = ChunkerStructureAwareNode(
        id="c", config=ChunkerStructureAwareConfig(target_tokens=256, max_tokens=512, min_tokens=0)
    )
    chunks = (await node.run(ChunkerConsumes(ir=ir))).chunks
    assert len(chunks) == 1
    assert chunks[0].block_ids == ["h1", "p1"]  # heading + its body, together
    assert chunks[0].heading_path == ["Populated"]
