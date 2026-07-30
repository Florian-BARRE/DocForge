"""SetStack: 0..3 simple contextualize methods, reordering, empty stack disables the stage, plus the
externalised llm method (prep -> ForEach(llm chain [+ keep_raw]) -> apply): its topology, its
SetStack->apply->read chain round-trip (1-step AND 2-step, idempotent), and REAL-VIEW parity (a fake
llm step that ECHOES the document view it received grows chunk.context exactly as the old monolith
did, with the view mattering — section AND full scope).
"""

import itertools

import pytest

from shared_libs.pipelines.base import (
    FromGroupInput,
    FromNode,
    NodeConfig,
)
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.build.blob import ActionNodeBlob, ForEachNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragmentBuilder, ChainStepSpec
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.nodes.contextualize.base import (
    ContextualizeViewHelpers,
    DocumentScope,
)
from shared_libs.pipelines.ingest.stages import (
    ChainSpec,
    ChainStep,
    SetStack,
    StackMethod,
    StateReader,
)
from shared_libs.pipelines.nodes.llm.base import BaseLlmChatNode, LlmChatProduces
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk
from shared_libs.public_models.llm import Completion

_METHODS = ["doc_meta", "breadcrumb", "sliding"]
_ALL_PERMUTATIONS = list(
    itertools.chain.from_iterable(
        itertools.permutations(_METHODS, r) for r in range(0, len(_METHODS) + 1)
    )
)

FAKE_ECHO_LLM = "test_stack_echo_llm"


# ---------------------------------------------------------------------------
# Simple (non-llm) methods — unchanged single-node stack semantics.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("combo", _ALL_PERMUTATIONS, ids=lambda c: "-".join(c) or "empty")
def test_every_stack_permutation_validates_and_orders_correctly(
    compiler, builder, validator, combo
) -> None:
    default = IngestPipeline.default_blob()
    steps = [StackMethod(kind=kind, config={}) for kind in combo]
    restacked, notices = compiler.apply(default, SetStack(stage="contextualize", steps=steps))
    assert validator.validate(builder.build(restacked)) == [], (combo, notices)

    read_back = StateReader.read(restacked)
    assert [m.kind for m in read_back.stack] == list(combo)

    if not combo:
        assert notices  # emptying the stack is flagged
        return

    # The chain order: chunk -> first method -> second -> ... in application order.
    ctx_ids = [n.id for n in restacked.nodes if getattr(n, "family", None) == "contextualize"]
    assert len(ctx_ids) == len(combo)
    assert restacked.bindings[ctx_ids[0]]["chunks"] == FromNode(
        node_id="chunk", field_name="chunks"
    )
    for previous, current in zip(ctx_ids, ctx_ids[1:], strict=False):
        assert restacked.bindings[current]["chunks"] == FromNode(
            node_id=previous, field_name="chunks"
        )


def test_empty_stack_disables_the_contextualize_stage(compiler) -> None:
    default = IngestPipeline.default_blob()
    emptied, notices = compiler.apply(default, SetStack(stage="contextualize", steps=[]))
    assert "contextualize stack emptied" in " ".join(notices)
    read_back = StateReader.read(emptied)
    assert read_back.stack == []


def test_unknown_stack_method_is_a_notice_not_a_raise(compiler) -> None:
    """An unknown method kind is DATA — the stack is left unchanged with a notice, never a 500."""
    default = IngestPipeline.default_blob()
    before = StateReader.read(default).stack

    result, notices = compiler.apply(
        default, SetStack(stage="contextualize", steps=[StackMethod(kind="does_not_exist")])
    )

    assert "does_not_exist" in " ".join(notices)
    assert StateReader.read(result).stack == before  # unchanged, no partial mutation


# ---------------------------------------------------------------------------
# The llm method — externalised topology (prep / loop / apply / keep_raw) + repeated distinct ids.
# ---------------------------------------------------------------------------


def _llm(document_scope: str = "section", chain: list[ChainStep] | None = None) -> StackMethod:
    return StackMethod(
        kind="llm",
        config={"document_scope": document_scope},
        chain=ChainSpec(family="llm", steps=chain) if chain else None,
    )


def test_single_llm_position_emits_prep_loop_apply_with_keep_raw(
    compiler, builder, validator
) -> None:
    default = IngestPipeline.default_blob()
    restacked, notices = compiler.apply(default, SetStack(stage="contextualize", steps=[_llm()]))
    assert validator.validate(builder.build(restacked)) == [], notices

    by_id = {n.id: n for n in restacked.nodes}
    assert isinstance(by_id["ctx_llm"], ActionNodeBlob) and by_id["ctx_llm"].kind == "llm"
    assert isinstance(by_id["ctx_llm_loop"], ForEachNodeBlob)
    assert (
        isinstance(by_id["ctx_llm_apply"], ActionNodeBlob)
        and by_id["ctx_llm_apply"].kind == "llm_apply"
    )
    # The loop iterates the prep's prompts.
    assert isinstance(by_id["ctx_llm_loop"].over, FromNode)
    assert by_id["ctx_llm_loop"].over.node_id == "ctx_llm"
    # apply merges the loop's completions onto the SAME incoming chunks the prep read.
    assert restacked.bindings["ctx_llm_apply"]["chunks"] == FromNode(
        node_id="chunk", field_name="chunks"
    )
    assert restacked.bindings["ctx_llm_apply"]["completions"] == FromNode(
        node_id="ctx_llm_loop", field_name="items"
    )
    # keep_raw is the fail-soft terminal inside the loop body (default on_error).
    assert any(getattr(n, "kind", None) == "keep_raw" for n in by_id["ctx_llm_loop"].body.nodes)


def test_two_llm_positions_get_distinct_prep_loop_apply_ids(compiler, builder, validator) -> None:
    default = IngestPipeline.default_blob()
    restacked, notices = compiler.apply(
        default, SetStack(stage="contextualize", steps=[_llm("section"), _llm("full")])
    )
    assert validator.validate(builder.build(restacked)) == [], notices
    ids = {n.id for n in restacked.nodes}
    for expected in (
        "ctx_llm",
        "ctx_llm_loop",
        "ctx_llm_apply",
        "ctx_llm_2",
        "ctx_llm_2_loop",
        "ctx_llm_2_apply",
    ):
        assert expected in ids, expected
    # The second position reads the first position's output (its apply's chunks).
    assert restacked.bindings["ctx_llm_2"]["chunks"] == FromNode(
        node_id="ctx_llm_apply", field_name="chunks"
    )


# ---------------------------------------------------------------------------
# SetStack -> apply -> read chain round-trip (idempotent), 1-step and 2-step.
# ---------------------------------------------------------------------------


def _endpoint(url: str) -> dict:
    return {"base_url": url, "api_key": "k", "model": "m"}


@pytest.mark.parametrize(
    "chain_steps",
    [
        [ChainStep(kind="openai_compatible", config=_endpoint("http://a"))],
        [
            ChainStep(kind="openai_compatible", config=_endpoint("http://a")),
            ChainStep(kind="mistral", config={"api_key": "k"}),
        ],
    ],
    ids=["1-step", "2-step"],
)
def test_llm_chain_round_trips_and_is_idempotent(compiler, builder, validator, chain_steps) -> None:
    default = IngestPipeline.default_blob()
    once, _ = compiler.apply(
        default, SetStack(stage="contextualize", steps=[_llm("section", chain_steps)])
    )
    assert validator.validate(builder.build(once)) == []

    read_once = StateReader.read(once)
    assert len(read_once.stack) == 1
    method = read_once.stack[0]
    assert method.kind == "llm"
    assert method.chain is not None
    assert [s.kind for s in method.chain.steps] == [s.kind for s in chain_steps]

    # Re-applying the read-back stack reproduces an IDENTICAL blob (compile -> read -> compile stable).
    twice, _ = compiler.apply(once, SetStack(stage="contextualize", steps=read_once.stack))
    assert twice.model_dump(mode="json") == once.model_dump(mode="json")


# ---------------------------------------------------------------------------
# REAL-VIEW parity — a fake llm that ECHOES the document view it received, so the view MATTERS.
# ---------------------------------------------------------------------------


class _EchoConfig(NodeConfig):
    """No knobs — the echo llm needs no endpoint."""


@NodeRegistry.register("llm")
class EchoLlmNode(BaseLlmChatNode):
    """Answers with the DOCUMENT VIEW the prep built (recovered from the prompt) — the view matters."""

    KIND = FAKE_ECHO_LLM
    NAME = "E"
    SUMMARY = "e"
    Config = _EchoConfig

    def _chat_model(self):  # pragma: no cover - never called
        raise NotImplementedError

    async def run(self, data) -> LlmChatProduces:
        content = str(data.prompt.messages[-1].content)
        view = content.split("<document>\n", 1)[1].rsplit("\n</document>", 1)[0]
        return LlmChatProduces(completion=Completion(text=f"VIEW::{view}"))


def _echo_chunk(n: int, text: str, path: list[str] | None = None) -> Chunk:
    return Chunk(chunk_id=f"d#c{n}", ordinal=n, text=text, heading_path=path or [])


_PARITY_CHUNKS = [
    _echo_chunk(0, "Cats are small felines that purr.", ["Animals", "Cats"]),
    _echo_chunk(1, "They sleep most of the day and hunt at night.", ["Animals", "Cats"]),
    _echo_chunk(2, "Bond markets rose this quarter.", ["Finance"]),
    _echo_chunk(3, "No section here."),
]


def _standalone_llm_blob(prep_config: dict) -> dict:
    """A minimal prep(llm) -> ForEach(echo chain) -> apply blob reading the run chunks directly."""
    fragment = ChainFragmentBuilder.build(
        prefix="ctx",
        family="llm",
        steps=[ChainStepSpec(kind=FAKE_ECHO_LLM, config={})],
        step_inputs={"prompt": FromGroupInput(field_name="prompt")},
        output_field="completion",
        scored=False,
    )
    body = GroupNodeBlob(
        id="ctx_path",
        nodes=list(fragment.nodes),
        transitions=list(fragment.transitions),
        bindings=dict(fragment.bindings),
    )
    return {
        "node_type": "group",
        "id": "contextualize_llm",
        "nodes": [
            {
                "node_type": "action",
                "id": "prep",
                "family": "contextualize",
                "kind": "llm",
                "config": prep_config,
            },
            {
                "node_type": "foreach",
                "id": "loop",
                "item_field": "prompt",
                "max_concurrency": 4,
                "over": {"source": "node", "node_id": "prep", "field_name": "prompts"},
                "body": body.model_dump(),
            },
            {
                "node_type": "action",
                "id": "apply",
                "family": "contextualize",
                "kind": "llm_apply",
                "config": {},
            },
        ],
        "transitions": [
            {"from_node_id": "prep", "to_node_id": "loop"},
            {"from_node_id": "loop", "to_node_id": "apply"},
        ],
        "bindings": {
            "prep": {"chunks": {"source": "run", "field_name": "chunks"}},
            "apply": {
                "chunks": {"source": "run", "field_name": "chunks"},
                "completions": {"source": "node", "node_id": "loop", "field_name": "items"},
            },
        },
    }


def _reference_view_contexts(
    chunks: list[Chunk], scope: str, window: int, max_words: int
) -> list[str]:
    """What the monolith would have grown: VIEW:: + the SAME scoped view the helpers build per chunk."""
    full_view = (
        ContextualizeViewHelpers.full_view(chunks, max_words)
        if scope == DocumentScope.FULL
        else None
    )
    return [
        f"VIEW::{ContextualizeViewHelpers.scoped_view(index, chunks, DocumentScope(scope), window, max_words, full_view)}"
        for index in range(len(chunks))
    ]


@pytest.mark.parametrize("scope,window", [("section", 1), ("full", 2)])
async def test_real_view_parity_section_and_full(scope, window) -> None:
    """The echo llm grows chunk.context from the ACTUAL view — proving the prep's view flows through."""
    blob = _standalone_llm_blob({"document_scope": scope, "window_chunks": window})
    group = PipelineBuilder().build(blob)
    output, _record = await FlowEngine().execute(group, {"chunks": _PARITY_CHUNKS})
    assert output is not None
    grown = [chunk.context for chunk in output.chunks]
    assert grown == _reference_view_contexts(_PARITY_CHUNKS, scope, window, 4000)
