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
    assert out.chunks[0].context == "Section: Animals > Cats"
    assert out.chunks[3].context == ""  # no section -> nothing
    assert out.chunks[0].text == CHUNKS[0].text  # raw untouched
    assert CHUNKS[0].context == ""  # input copies, never mutated
    assert out.chunks[0].enriched_text.startswith("Section: Animals > Cats\n\n")


async def test_breadcrumb_max_depth_truncates_the_trail() -> None:
    node = ContextualizerBreadcrumbNode(id="b", config=ContextualizerBreadcrumbConfig(max_depth=1))
    out = await node.run(ContextualizerConsumes(chunks=CHUNKS))
    assert out.chunks[0].context == "Section: Cats"


SOURCE = SourceDocument(filename="r.pdf", content=b"x",
                        declared_meta={"title": "Annual Report", "author": "ACME", "year": 2024})


async def test_doc_meta_selected_fields() -> None:
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig(fields=["title", "author"]))
    out = await node.run(DocMetaConsumes(chunks=CHUNKS, source=SOURCE))
    assert out.chunks[0].context == "title: Annual Report · author: ACME"


async def test_doc_meta_defaults_to_all_declared_fields() -> None:
    node = ContextualizerDocMetaNode(id="m", config=ContextualizerDocMetaConfig())
    out = await node.run(DocMetaConsumes(chunks=CHUNKS, source=SOURCE))
    assert "year: 2024" in out.chunks[0].context


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
