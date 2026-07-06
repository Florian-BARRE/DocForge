"""Contextualize stage: 4 stackable methods, LLM scopes + keep_raw, stacked blob prefix order,
and the UNIQUE_IN_GRAPH doctrine (singletons rejected on duplication, repeatables pass).

Ported from the scratchpad's test_contextualize_stage.py.
"""

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
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
from shared_libs.pipelines.ingest.nodes.contextualize.llm import (
    ContextualizerLlmConfig,
    ContextualizerLlmNode,
)
from shared_libs.pipelines.ingest.nodes.contextualize.sliding import (
    ContextualizerSlidingConfig,
    ContextualizerSlidingNode,
)
from shared_libs.pipelines.registry import NodeRegistry
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


SEEN_DOCS: dict[str, str] = {}


@NodeRegistry.register("contextualize")
class FakeLlm(ContextualizerLlmNode):
    KIND = "test_contextualize_fake_llm"
    NAME = "F"
    SUMMARY = "t"

    async def _situate(self, document: str, chunk_text: str) -> str:
        if "sharply" in chunk_text:
            raise RuntimeError("model 503")
        SEEN_DOCS[chunk_text[:12]] = document
        return f"SITUATED[{chunk_text[:8]}]"


async def test_llm_context_section_scope_and_window_fallback_and_keep_raw() -> None:
    SEEN_DOCS.clear()
    cfg = ContextualizerLlmConfig(base_url="http://fake", model="fake", document_scope="section", window_chunks=1)
    out = await FakeLlm(id="l", config=cfg).run(ContextualizerConsumes(chunks=CHUNKS))

    # section scope: chunk 0's document view = its section siblings (chunks 0+1), not Finance
    assert "purr" in SEEN_DOCS["Cats are sma"]
    assert "sleep" in SEEN_DOCS["Cats are sma"]
    assert "Bond" not in SEEN_DOCS["Cats are sma"]
    # section-less chunk 3 fell back to the window scope (neighbour 2 included)
    assert "Bond markets" in SEEN_DOCS["No section h"]
    # keep_raw: the failing chunk (2) stayed raw, the document survived
    assert out.chunks[2].context == ""
    assert out.chunks[0].context == "SITUATED[Cats are]"


async def test_llm_context_on_error_fail_raises_in_strict_mode() -> None:
    strict = ContextualizerLlmConfig(base_url="http://fake", model="fake", on_error="fail")
    with pytest.raises(RuntimeError):
        await FakeLlm(id="l", config=strict).run(ContextualizerConsumes(chunks=CHUNKS))


async def test_f1_f2_full_scope_view_precomputed_once_and_structure_preserved() -> None:
    SEEN_DOCS.clear()
    full_cfg = ContextualizerLlmConfig(base_url="http://fake", model="fake", document_scope="full")
    safe_chunks = [c for c in CHUNKS if "sharply" not in c.text]
    await FakeLlm(id="l", config=full_cfg).run(ContextualizerConsumes(chunks=safe_chunks))
    views = list(SEEN_DOCS.values())
    assert all(view is views[0] for view in views), "full view must be built ONCE and reused"
    assert "\n\n" in views[0], "structure must be preserved under the cap"


async def test_stacked_blob_wires_meta_then_breadcrumb_then_llm_in_prefix_order() -> None:
    kinds = NodeRegistry.kinds("contextualize")
    assert {"breadcrumb", "doc_meta", "sliding", "llm"} <= set(kinds)

    blob = {
        "node_type": "group", "id": "ctx_stage",
        "nodes": [
            {"node_type": "action", "id": "meta", "family": "contextualize", "kind": "doc_meta",
             "config": {"fields": ["title"]}},
            {"node_type": "action", "id": "crumb", "family": "contextualize", "kind": "breadcrumb", "config": {}},
            {"node_type": "action", "id": "situate", "family": "contextualize",
             "kind": "test_contextualize_fake_llm", "config": {"base_url": "http://fake", "model": "fake"}},
        ],
        "transitions": [
            {"from_node_id": "meta", "to_node_id": "crumb"},
            {"from_node_id": "crumb", "to_node_id": "situate"},
        ],
        "bindings": {
            "meta": {"chunks": {"source": "run", "field_name": "chunks"},
                     "source": {"source": "run", "field_name": "source"}},
            "crumb": {"chunks": {"source": "node", "node_id": "meta", "field_name": "chunks"}},
            "situate": {"chunks": {"source": "node", "node_id": "crumb", "field_name": "chunks"}},
        },
    }
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    output, _record = await FlowEngine().execute(group, {"chunks": CHUNKS, "source": SOURCE})
    lines = output.chunks[0].context.split("\n")
    assert lines == ["title: Annual Report", "Section: Animals > Cats", "SITUATED[Cats are]"]
    assert output.chunks[0].text == CHUNKS[0].text


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
