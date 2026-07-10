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


SOURCE = SourceDocument(filename="r.pdf", content=b"x",
                        declared_meta={"title": "Annual Report", "author": "ACME", "year": 2024})
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
        Chunk(chunk_id="d#c0", ordinal=0, text="Marge en hausse.",
              heading_path=["Analyse financière", "Marge brute"]),
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
    node = ContextualizerSlidingNode(id="s", config=ContextualizerSlidingConfig(prev_words=3, next_words=2))
    out = await node.run(ContextualizerConsumes(chunks=CHUNKS))
    assert out.chunks[0].context == "They sleep …"  # head of next only (no prev)
    assert out.chunks[1].context == "… felines that purr.\nBond markets …"


def test_describe_exposes_the_scope_rules_to_the_ui() -> None:
    described = ContextualizerLlmNode.describe()
    for key in ("document_scope", "window_chunks", "max_document_words", "max_concurrency", "on_error"):
        assert key in described.config_schema["properties"], key


def test_unique_in_graph_doctrine_rejects_duplicated_singletons() -> None:
    assert ContextualizerBreadcrumbNode.describe().unique_in_graph is True
    assert ContextualizerLlmNode.describe().unique_in_graph is False  # two situating passes = legit

    dup = {
        "node_type": "group", "id": "dup",
        "nodes": [
            {"node_type": "action", "id": "b1", "family": "contextualize", "kind": "breadcrumb", "config": {}},
            {"node_type": "action", "id": "b2", "family": "contextualize", "kind": "breadcrumb", "config": {}},
        ],
        "transitions": [{"from_node_id": "b1", "to_node_id": "b2"}],
        "bindings": {"b1": {"chunks": {"source": "run", "field_name": "chunks"}},
                     "b2": {"chunks": {"source": "node", "node_id": "b1", "field_name": "chunks"}}},
    }
    codes = {issue.code.value for issue in GraphValidator().validate(PipelineBuilder().build(dup))}
    assert "duplicate_unique_node" in codes
