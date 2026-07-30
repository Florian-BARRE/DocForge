"""Contextualize stage: the pure stackable methods (breadcrumb / doc_meta / sliding), the llm method's
described scope rules, and the UNIQUE_IN_GRAPH doctrine (singletons rejected on duplication, the llm
method repeatable). The llm method's runtime behaviour (per-chunk situating, keep_raw, full scope) now
lives in the externalised topology, covered by test_contextualize_topology.py and test_stack.py.
"""

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest.nodes.contextualize.base import ContextualizerConsumes
from shared_libs.pipelines.ingest.nodes.contextualize.breadcrumb import (
    ContextualizerBreadcrumbConfig,
    ContextualizerBreadcrumbNode,
)
from shared_libs.pipelines.ingest.nodes.contextualize.doc_meta import (
    ContextualizerDocMetaConfig,
    ContextualizerDocMetaNode,
)
from shared_libs.pipelines.ingest.nodes.contextualize.doc_meta.core import DocMetaConsumes
from shared_libs.pipelines.ingest.nodes.contextualize.llm import ContextualizerLlmNode
from shared_libs.pipelines.ingest.nodes.contextualize.sliding import (
    ContextualizerSlidingConfig,
    ContextualizerSlidingNode,
)
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import Chunk, SourceDocument


def _chunk(n: int, text: str, path: list[str] | None = None) -> Chunk:
    return Chunk(chunk_id=f"d#c{n}", ordinal=n, text=text, heading_path=path or [])


CHUNKS = [
    _chunk(0, "Cats are small felines that purr.", ["Animals", "Cats"]),
    _chunk(1, "They sleep most of the day and hunt at night.", ["Animals", "Cats"]),
    _chunk(2, "Bond markets fell sharply this quarter.", ["Finance"]),
    _chunk(3, "No section here."),
]


async def test_breadcrumb_renders_the_section_trail() -> None:
    node = ContextualizerBreadcrumbNode(id="b", config=ContextualizerBreadcrumbConfig())
    out = await node.run(ContextualizerConsumes(chunks=CHUNKS))
    assert out.chunks[0].context == "Animals › Cats"  # no "Section:" noise
    assert out.chunks[3].context == ""  # no section -> nothing
    assert out.chunks[0].text == CHUNKS[0].text  # raw untouched
    assert CHUNKS[0].context == ""  # input copies, never mutated
    assert out.chunks[0].enriched_text.startswith("Animals › Cats\n\n")


async def test_breadcrumb_max_depth_truncates_the_trail() -> None:
    node = ContextualizerBreadcrumbNode(id="b", config=ContextualizerBreadcrumbConfig(max_depth=1))
    out = await node.run(ContextualizerConsumes(chunks=CHUNKS))
    assert out.chunks[0].context == "Cats"


SOURCE = SourceDocument(
    filename="r.pdf",
    content=b"x",
    declared_meta={"title": "Annual Report", "author": "ACME", "year": 2024},
)
NO_TITLE = SourceDocument(filename="r.pptx", content=b"x", declared_meta={})


async def test_doc_meta_anchors_on_the_declared_title() -> None:
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    out = await node.run(DocMetaConsumes(chunks=CHUNKS, source=SOURCE))
    assert all(chunk.context == "Annual Report" for chunk in out.chunks)  # one anchor, every chunk


async def test_doc_meta_falls_back_to_the_first_level_one_heading() -> None:
    # (C) No declared title (e.g. the PPTX parser sets none) → anchor on the first top-level heading.
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    out = await node.run(DocMetaConsumes(chunks=CHUNKS, source=NO_TITLE))
    assert all(chunk.context == "Animals" for chunk in out.chunks)  # CHUNKS[0].heading_path[0]


# A FLAT document (all headings level-1, no real hierarchy — the HTML->PDF case): the first chunk
# coalesces the title-section with the next sibling sections, so its COMMON heading_path is []. The
# regression: the old fallback picked "the first chunk WITH a heading_path", wrongly anchoring every
# chunk on a LATER section (e.g. "Section 3") and corrupting search. The anchor must be the TRUE
# first heading (the title), read off the IR, or nothing — never a later section.
_FLAT_CHUNKS = [
    _chunk(0, "Intro paragraph and first two sections merged.", []),  # coalesced siblings -> []
    _chunk(1, "Ingress traffic terminates at the edge.", ["Section 3. Ingress"]),
    _chunk(2, "Services register with the mesh registry.", ["Section 4. Discovery"]),
]


def _flat_ir():
    from shared_libs.public_models import Block, BlockType, DocumentIR, Provenance

    def _b(bid, btype, order, text, parent=None):
        return Block(
            id=bid,
            block_type=btype,
            reading_order=order,
            parent_id=parent,
            level=1 if btype == BlockType.HEADING else None,
            provenance=Provenance(page=0, bbox=(0.1, 0.1, 0.9, 0.9)),
            text=text,
        )

    return DocumentIR(
        doc_id="net",
        source_hash="h",
        n_pages=1,
        blocks=[
            _b("h0", BlockType.HEADING, 0, "Acme Platform Networking Guide"),
            _b("t1", BlockType.PARAGRAPH, 1, "Intro.", parent="h0"),
            _b("h6", BlockType.HEADING, 6, "Section 3. Ingress"),
            _b("t7", BlockType.PARAGRAPH, 7, "Ingress.", parent="h6"),
        ],
    )


async def test_doc_meta_anchor_on_flat_doc_is_the_true_title_not_a_later_section() -> None:
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    # With the IR, the anchor is the document's real first heading — NOT "Section 3".
    out = await node.run(DocMetaConsumes(chunks=_FLAT_CHUNKS, source=NO_TITLE, ir=_flat_ir()))
    assert all(c.context == "Acme Platform Networking Guide" for c in out.chunks), [
        c.context for c in out.chunks
    ]


async def test_doc_meta_flat_doc_without_ir_never_anchors_on_a_later_section() -> None:
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    # No IR + first chunk has [] heading_path → emit no anchor rather than a wrong later section.
    out = await node.run(DocMetaConsumes(chunks=_FLAT_CHUNKS, source=NO_TITLE))
    assert not any(c.context for c in out.chunks), [c.context for c in out.chunks]


async def test_doc_meta_does_not_duplicate_an_anchor_the_chunk_already_opens_with() -> None:
    """When the chunker has inlined the title section into a coalesced first chunk, the doc anchor
    must NOT be prefixed again (no 'Title \\n Title' duplication); other chunks still get it."""
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    chunks = [
        _chunk(0, "Acme Glossary\n\nZero Trust\n\nA model where nothing is trusted.", []),
        _chunk(1, "Some later body text.", ["Acme Glossary"]),
    ]
    out = await node.run(
        DocMetaConsumes(
            chunks=chunks,
            source=SourceDocument(
                filename="g.html", content=b"x", declared_meta={"title": "Acme Glossary"}
            ),
        )
    )
    assert not out.chunks[0].context  # already opens with the title → no duplicate
    assert out.chunks[1].context == "Acme Glossary"  # a normal chunk still gets the anchor


async def test_doc_meta_anchor_not_dropped_when_body_merely_starts_with_the_title_word() -> None:
    """The dedup compares the FIRST LINE, not a bare prefix: a chunk whose prose merely opens with
    the title word (title 'Overview', body 'Overview of the topology…') must STILL get the anchor —
    only a chunk whose first line IS the title (the chunker-inlined case) is skipped."""
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    src = SourceDocument(filename="d.html", content=b"x", declared_meta={"title": "Overview"})
    chunks = [
        _chunk(0, "Overview of the deployment topology follows here.", []),  # prose, not the heading
        _chunk(1, "Overview\n\nThe deployment topology follows here.", []),  # inlined heading line
    ]
    out = await node.run(DocMetaConsumes(chunks=chunks, source=src))
    assert out.chunks[0].context == "Overview"  # prose start → anchor NOT dropped (the regression)
    assert not out.chunks[1].context  # first line is exactly the title → correctly skipped


async def test_doc_meta_ir_fallback_skips_a_toc_heading_and_a_subheading() -> None:
    """The IR-fallback title must be the first TOP-LEVEL (level-1), non-ToC heading — not a ToC
    heading that opens the document, nor a deeper subheading."""
    from shared_libs.public_models import Block, BlockType, DocumentIR, Provenance

    def _b(bid, order, text, level):
        return Block(
            id=bid,
            block_type=BlockType.HEADING,
            reading_order=order,
            level=level,
            provenance=Provenance(page=0, bbox=(0.1, 0.1, 0.9, 0.9)),
            text=text,
        )

    ir = DocumentIR(
        doc_id="d",
        source_hash="h",
        n_pages=1,
        blocks=[
            _b("toc", 0, "Table of Contents", 1),  # furniture — must be skipped
            _b("sub", 1, "1.1 Scope", 2),  # a subheading — not top-level
            _b("title", 2, "Data Protection Regulation", 1),  # the real title
        ],
    )
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    out = await node.run(DocMetaConsumes(chunks=_FLAT_CHUNKS, source=NO_TITLE, ir=ir))
    assert all(c.context == "Data Protection Regulation" for c in out.chunks), [
        c.context for c in out.chunks
    ]


async def _default_stack(chunks: list[Chunk], source: SourceDocument) -> list[Chunk]:
    """Run the stock zero-cost stack (doc_meta → breadcrumb) exactly as the default blob wires it."""
    meta = await ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig()).run(
        DocMetaConsumes(chunks=chunks, source=source)
    )
    trail = await ContextualizerBreadcrumbNode(id="b", config=ContextualizerBreadcrumbConfig()).run(
        ContextualizerConsumes(chunks=meta.chunks)
    )
    return trail.chunks


async def test_default_stack_builds_one_anchored_trail_nested() -> None:
    # (B) Nested headings → the full "<doc> › A › B" trail on ONE clean line, no duplicate title.
    chunks = [
        Chunk(
            chunk_id="d#c0",
            ordinal=0,
            text="Marge en hausse.",
            heading_path=["Analyse financière", "Marge brute"],
        ),
    ]
    out = await _default_stack(chunks, NO_TITLE)  # anchor = first level-1 heading here
    assert out[0].context == "Analyse financière › Marge brute"  # anchor IS heading_path[0]: no dup


async def test_default_stack_flat_deck_anchors_each_slide() -> None:
    # (D) Flat deck (all level-1) → "<doc anchor> › <slide title>", no dup, no empty "Section:".
    deck = [
        Chunk(chunk_id="d#c0", ordinal=0, text="Titre.", heading_path=["Rapport annuel 2026"]),
        Chunk(chunk_id="d#c1", ordinal=1, text="Marge.", heading_path=["Marge brute"]),
    ]
    out = await _default_stack(deck, NO_TITLE)
    assert out[0].context == "Rapport annuel 2026"  # anchor slide: named once, not doubled
    assert out[1].context == "Rapport annuel 2026 › Marge brute"  # anchored, one clean trail


async def test_default_stack_declared_title_anchors_a_flat_deck() -> None:
    deck = [Chunk(chunk_id="d#c0", ordinal=0, text="Marge.", heading_path=["Marge brute"])]
    out = await _default_stack(deck, SOURCE)  # declared title beats the first heading
    assert out[0].context == "Annual Report › Marge brute"


async def test_sliding_context_uses_prev_tail_and_next_head() -> None:
    node = ContextualizerSlidingNode(
        id="s", config=ContextualizerSlidingConfig(prev_words=3, next_words=2)
    )
    out = await node.run(ContextualizerConsumes(chunks=CHUNKS))
    assert out.chunks[0].context == "They sleep …"  # head of next only (no prev)
    assert out.chunks[1].context == "… felines that purr.\nBond markets …"


def test_describe_exposes_the_scope_rules_to_the_ui() -> None:
    described = ContextualizerLlmNode.describe()
    for key in (
        "document_scope",
        "window_chunks",
        "max_document_words",
        "max_concurrency",
        "on_error",
    ):
        assert key in described.config_schema["properties"], key


def test_unique_in_graph_doctrine_rejects_duplicated_singletons() -> None:
    assert ContextualizerBreadcrumbNode.describe().unique_in_graph is True
    assert ContextualizerLlmNode.describe().unique_in_graph is False  # two situating passes = legit

    dup = {
        "node_type": "group",
        "id": "dup",
        "nodes": [
            {
                "node_type": "action",
                "id": "b1",
                "family": "contextualize",
                "kind": "breadcrumb",
                "config": {},
            },
            {
                "node_type": "action",
                "id": "b2",
                "family": "contextualize",
                "kind": "breadcrumb",
                "config": {},
            },
        ],
        "transitions": [{"from_node_id": "b1", "to_node_id": "b2"}],
        "bindings": {
            "b1": {"chunks": {"source": "run", "field_name": "chunks"}},
            "b2": {"chunks": {"source": "node", "node_id": "b1", "field_name": "chunks"}},
        },
    }
    codes = {issue.code.value for issue in GraphValidator().validate(PipelineBuilder().build(dup))}
    assert "duplicate_unique_node" in codes
