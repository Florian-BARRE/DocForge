"""The externalised llm-contextualize topology (prep -> ForEach(llm chain [+ keep_raw]) -> llm_apply),
the shape the contextualize LLM stage emits.

The old monolithic contextualizer node is GONE (P6b deleted it and made the prep the canonical
(contextualize, llm)), so parity is proven against a REFERENCE reconstructed from the same fake
situating function the monolith used (a chunk that carries the fail sentinel stays raw, every other
chunk grows the canned snippet). A FAKE llm kind returns canned completions (it recovers the chunk
text from the prompt the prep built), so the ONLY thing under test is the new topology. on_error is
verified as a GRAPH EDGE (a keep_raw terminal vs a propagating item failure), and the prep is verified
to emit one prompt per chunk, in order, never skipping.
"""

from shared_libs.pipelines.base import (
    FromGroupInput,
    NodeConfig,
    OnFailure,
    Transition,
)
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragmentBuilder, ChainStepSpec
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.contextualize.llm import (
    ContextualizerLlmConfig,
    ContextualizerLlmConsumes,
    ContextualizerLlmNode,
)
from shared_libs.pipelines.nodes.llm.base import BaseLlmChatNode, LlmChatProduces
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import Chunk
from shared_libs.public_models.llm import Completion

# ---------------------------------------------------------------------------
# Fixtures — the same chunks the contextualize stage test uses, so parity is judged on identical input.
# ---------------------------------------------------------------------------


def _chunk(n: int, text: str, path: list[str] | None = None) -> Chunk:
    return Chunk(chunk_id=f"d#c{n}", ordinal=n, text=text, heading_path=path or [])


CHUNKS = [
    _chunk(0, "Cats are small felines that purr.", ["Animals", "Cats"]),
    _chunk(1, "They sleep most of the day and hunt at night.", ["Animals", "Cats"]),
    _chunk(2, "Bond markets fell sharply this quarter.", ["Finance"]),
    _chunk(3, "No section here."),
]
SAFE_CHUNKS = [chunk for chunk in CHUNKS if "sharply" not in chunk.text]

FAIL_SENTINEL = "sharply"  # a chunk the fake situating call refuses (a simulated 503)
FAKE_LLM_KIND = "test_ctx_topology_fake_llm"


def _situate(chunk_text: str) -> str:
    """The canned situating snippet — depends on the CHUNK only, so a mis-order is detectable."""
    return f"SITUATED[{chunk_text[:8]}]"


def _reference_contexts(chunks: list[Chunk]) -> list[str]:
    """The grown context the OLD monolith would produce: the snippet per chunk, raw on the sentinel."""
    return ["" if FAIL_SENTINEL in chunk.text else _situate(chunk.text) for chunk in chunks]


def _chunk_text_of(prompt) -> str:
    """Recover the chunk text the prep embedded in the situating prompt's human message."""
    content = str(prompt.messages[-1].content)
    return content.split("<chunk>\n", 1)[1].rsplit("\n</chunk>", 1)[0]


class _FakeLlmConfig(NodeConfig):
    """No knobs — the fake situating call needs no endpoint."""


@NodeRegistry.register("llm")
class FakeLlmNode(BaseLlmChatNode):
    """Fulfils a situating prompt with a canned snippet; refuses a chunk carrying the sentinel."""

    KIND = FAKE_LLM_KIND
    NAME = "F"
    SUMMARY = "t"
    Config = _FakeLlmConfig

    def _chat_model(self):  # pragma: no cover - never called (run is overridden)
        raise NotImplementedError

    async def run(self, data) -> LlmChatProduces:
        chunk_text = _chunk_text_of(data.prompt)
        if FAIL_SENTINEL in chunk_text:
            raise RuntimeError("model 503")
        return LlmChatProduces(completion=Completion(text=_situate(chunk_text)))


# ---------------------------------------------------------------------------
# Blob assembly — the new topology as a dict blob (what the stage emits), body inlined here.
# ---------------------------------------------------------------------------


def _body(chain_steps: list[dict], keep_raw: bool) -> GroupNodeBlob:
    """The per-prompt ForEach body: an llm chain, plus a fail-soft keep_raw terminal when asked."""
    fragment = ChainFragmentBuilder.build(
        prefix="ctx",
        family="llm",
        steps=[ChainStepSpec(kind=step["kind"], config=step.get("config", {})) for step in chain_steps],
        step_inputs={"prompt": FromGroupInput(field_name="prompt")},
        output_field="completion",
        scored=False,  # llm is NON-scored -> escalate on failure only
    )
    nodes: list = list(fragment.nodes)
    transitions: list[Transition] = list(fragment.transitions)
    bindings: dict[str, dict] = dict(fragment.bindings)

    # keep_raw: the chain's last step routes here OnFailure -> empty completion -> chunk stays raw.
    if keep_raw:
        nodes.append(ActionNodeBlob(id="keep", family="contextualize", kind="keep_raw"))
        transitions.append(
            Transition(from_node_id=fragment.exits[-1], to_node_id="keep", condition=OnFailure())
        )
        bindings["keep"] = {"prompt": FromGroupInput(field_name="prompt")}

    return GroupNodeBlob(id="ctx_path", nodes=nodes, transitions=transitions, bindings=bindings)


def _blob(prep_config: dict, keep_raw: bool, chain_steps: list[dict] | None = None) -> dict:
    """prep(llm) -> ForEach(over=prep.prompts, item=prompt, llm chain [+ keep_raw]) -> llm_apply."""
    body = _body(chain_steps or [{"kind": FAKE_LLM_KIND}], keep_raw)
    return {
        "node_type": "group",
        "id": "contextualize_llm",
        "nodes": [
            {"node_type": "action", "id": "prep", "family": "contextualize", "kind": "llm",
             "config": prep_config},
            {"node_type": "foreach", "id": "loop", "item_field": "prompt", "max_concurrency": 4,
             "over": {"source": "node", "node_id": "prep", "field_name": "prompts"},
             "body": body.model_dump()},
            {"node_type": "action", "id": "apply", "family": "contextualize", "kind": "llm_apply",
             "config": {}},
        ],
        "transitions": [
            {"from_node_id": "prep", "to_node_id": "loop"},
            {"from_node_id": "loop", "to_node_id": "apply"},
        ],
        "bindings": {
            "prep": {"chunks": {"source": "run", "field_name": "chunks"}},
            "apply": {"chunks": {"source": "run", "field_name": "chunks"},
                      "completions": {"source": "node", "node_id": "loop", "field_name": "items"}},
        },
    }


async def _run_new(blob: dict, chunks: list[Chunk]) -> object:
    group = PipelineBuilder().build(blob)
    output, _record = await FlowEngine().execute(group, {"chunks": chunks})
    return output


# ---------------------------------------------------------------------------
# 1. BUILD + validate (keep_raw body and fail body).
# ---------------------------------------------------------------------------


def test_topology_builds_and_validates() -> None:
    group = PipelineBuilder().build(_blob({"document_scope": "section"}, keep_raw=True))
    assert GraphValidator().validate(group) == []


def test_fail_body_builds_and_validates() -> None:
    """No keep_raw terminal (on_error=fail) — a bare 1-step llm chain still validates."""
    group = PipelineBuilder().build(_blob({"document_scope": "section"}, keep_raw=False))
    assert GraphValidator().validate(group) == []


def test_fallback_chain_topology_builds_and_validates() -> None:
    """A 2-step llm chain (escalate on failure) + keep_raw terminal still validates."""
    chain = [{"kind": FAKE_LLM_KIND}, {"kind": "openai_compatible",
              "config": {"base_url": "http://robust", "api_key": "k", "model": "big"}}]
    group = PipelineBuilder().build(_blob({"document_scope": "section"}, True, chain))
    assert GraphValidator().validate(group) == []


# ---------------------------------------------------------------------------
# 2. Prep emits one prompt per chunk, in order, never skipping.
# ---------------------------------------------------------------------------


async def test_prep_emits_one_prompt_per_chunk_in_order() -> None:
    prep = ContextualizerLlmNode(id="p", config=ContextualizerLlmConfig(document_scope="section"))
    out = await prep.run(ContextualizerLlmConsumes(chunks=CHUNKS))
    assert len(out.prompts) == len(CHUNKS)
    # Each prompt carries its OWN chunk's text, in order — the join key the apply node zips on.
    assert [_chunk_text_of(prompt) for prompt in out.prompts] == [chunk.text for chunk in CHUNKS]


# ---------------------------------------------------------------------------
# 3. Parity with the reconstructed reference — same grown chunk.context (order-correct, keep_raw).
# ---------------------------------------------------------------------------


async def test_topology_matches_reference_section_scope() -> None:
    """1-step chain + order-correct application + keep_raw in one comparison: new == reference."""
    new = await _run_new(_blob({"document_scope": "section", "window_chunks": 1}, keep_raw=True), CHUNKS)
    assert new is not None
    assert [chunk.context for chunk in new.chunks] == _reference_contexts(CHUNKS)
    # order-correct: each chunk grew with ITS OWN snippet (a mis-order would swap these).
    assert new.chunks[0].context == "SITUATED[Cats are]"
    assert new.chunks[1].context == "SITUATED[They sle]"
    # keep_raw: the sentinel chunk (2) stayed raw, the document survived.
    assert new.chunks[2].context == ""


async def test_topology_matches_reference_full_scope() -> None:
    new = await _run_new(_blob({"document_scope": "full"}, keep_raw=True), SAFE_CHUNKS)
    assert [chunk.context for chunk in new.chunks] == _reference_contexts(SAFE_CHUNKS)


# ---------------------------------------------------------------------------
# 4. on_error as a graph edge — keep_raw terminal vs a propagating item failure.
# ---------------------------------------------------------------------------


async def test_keep_raw_survives_a_failed_chunk() -> None:
    output = await _run_new(_blob({"document_scope": "section"}, keep_raw=True), CHUNKS)
    assert output is not None  # the run completed
    assert output.chunks[2].context == ""  # the failed chunk stayed raw
    assert output.chunks[0].context == "SITUATED[Cats are]"


async def test_fail_propagates_as_an_item_failure() -> None:
    """fail: no keep_raw terminal, so the failed chunk fails the ForEach item and the whole run."""
    group = PipelineBuilder().build(_blob({"document_scope": "section"}, keep_raw=False))
    output, record = await FlowEngine().execute(group, {"chunks": CHUNKS})
    assert output is None
    assert record.status.value == "failed"
