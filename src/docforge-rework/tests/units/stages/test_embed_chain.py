"""Embed as a NON-scored, UNIQUE-capped fallback chain (bge_server → openai_compatible): a >1-step
embed chain build/validates, wires OnFailure-only escalation (NO ScoreBelow) with a best-first join,
and round-trips through the reader. Both embedders are UNIQUE_IN_GRAPH, so a chain may only mix the
two DIFFERENT kinds — a duplicate is rejected. A score_below on an embed step is dropped (embed is
failure-only). SetProvider(embed) stays 1-step sugar.

Both kinds are real registered embedders — no fake node needed (unlike parse, whose only real kind
is docling).
"""

from shared_libs.pipelines.base import FromFirst, FromNode, OnFailure, OnSuccess, ScoreBelow
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import (
    ChainSpec,
    ChainStep,
    IngestAssembler,
    SetChain,
    SetProvider,
    StateReader,
    default_state,
)

BGE = "bge_server"
OAI = "openai_compatible"


def _two_step_chain(compiler, steps=None):
    """Compile the default blob with a 2-step embed chain (bge_server → openai_compatible)."""
    default = IngestPipeline.default_blob()
    steps = steps or [ChainStep(kind=BGE), ChainStep(kind=OAI)]
    return compiler.apply(default, SetChain(stage="embed", slot=None, steps=steps))


def _edges(blob, from_id, to_id):
    """The transition condition types on every edge from_id → to_id in the top-level blob."""
    return [
        type(t.condition)
        for t in blob.transitions
        if t.from_node_id == from_id and t.to_node_id == to_id
    ]


def test_two_step_embed_chain_builds_and_validates(compiler, builder, validator) -> None:
    chained, notices = _two_step_chain(compiler)
    assert validator.validate(builder.build(chained)) == [], notices


def test_two_step_embed_chain_is_failure_only_with_best_first_join(compiler) -> None:
    chained, _ = _two_step_chain(compiler)
    node_ids = {n.id for n in chained.nodes}
    assert {"embed_0", "embed_1"} <= node_ids and "embed" not in node_ids

    # 1. Non-scored family → step 0 falls through on failure ONLY (no ScoreBelow escalation).
    escalation = _edges(chained, "embed_0", "embed_1")
    assert OnFailure in escalation
    assert ScoreBelow not in escalation
    assert not any(isinstance(t.condition, ScoreBelow) for t in chained.transitions)

    # 2. Either embedder, on success, exits to the delivery bundle (embed is the last stage).
    assert OnSuccess in _edges(chained, "embed_0", "bundle")
    assert OnSuccess in _edges(chained, "embed_1", "bundle")

    # 3. bundle.embeddings reads whichever embedder answered — best (last) first.
    join = chained.bindings["bundle"]["embeddings"]
    assert isinstance(join, FromFirst)
    assert [c.node_id for c in join.candidates] == ["embed_1", "embed_0"]

    # 4. Each step consumes the SAME face (chunks spine + contract), threaded by the assembler.
    for step_id in ("embed_0", "embed_1"):
        assert set(chained.bindings[step_id]) == {"chunks", "contract"}


def test_reader_round_trips_the_embed_chain(compiler) -> None:
    chained, _ = _two_step_chain(compiler)
    state = StateReader.read(chained)
    assert state.embed_chain.family == "embed"
    assert [s.kind for s in state.embed_chain.steps] == [BGE, OAI]
    assert all(s.score_below is None for s in state.embed_chain.steps)


def test_score_below_on_embed_step_is_dropped_with_a_notice(compiler) -> None:
    chained, notices = _two_step_chain(
        compiler, steps=[ChainStep(kind=BGE, score_below=0.5), ChainStep(kind=OAI)]
    )
    assert any("failure-only" in n for n in notices)
    # The threshold is gone from the stored chain and no ScoreBelow edge was emitted.
    state = StateReader.read(chained)
    assert all(s.score_below is None for s in state.embed_chain.steps)
    assert not any(isinstance(t.condition, ScoreBelow) for t in chained.transitions)


def test_duplicate_unique_embedder_is_a_notice_and_the_build_rejects_it(compiler, builder, validator) -> None:
    chained, notices = _two_step_chain(compiler, steps=[ChainStep(kind=BGE), ChainStep(kind=BGE)])
    assert any("only once" in n for n in notices)
    # The blob is still assembled (data), but the validator rejects the duplicate unique node.
    issues = validator.validate(builder.build(chained))
    assert issues != []


def test_set_provider_embed_is_one_step_chain_sugar(compiler) -> None:
    default = IngestPipeline.default_blob()
    swapped, _ = compiler.apply(default, SetProvider(stage="embed", kind=BGE))
    state = StateReader.read(swapped)
    assert len(state.embed_chain.steps) == 1
    assert state.embed_chain.steps[0].kind == BGE
    # A single provider stays the stock lone 'embed' node with a plain FromNode anchor.
    assert any(n.id == "embed" for n in swapped.nodes)
    assert swapped.bindings["bundle"]["embeddings"] == FromNode(node_id="embed", field_name="embeddings")


def test_set_provider_embed_unknown_kind_is_a_notice_not_an_exception(compiler) -> None:
    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(default, SetProvider(stage="embed", kind="bogus"))
    assert unchanged == default
    assert any("'bogus' is not a 'embed' provider" in n for n in notices)


def test_two_step_embed_chain_from_assembler_matches_wiring(builder, validator) -> None:
    # Direct assembly (no compiler) — proves the SegmentBuilder emits the same failure-only chain.
    # Configs carry the required fields explicitly (the compiler fills these build-safe; here we set
    # them so the raw assembled blob builds without the compiler's config completion).
    endpoint = {"base_url": "http://embed:8000/v1", "model": "m"}
    state = default_state().model_copy(update={
        "embed_chain": ChainSpec(
            family="embed",
            steps=[ChainStep(kind=BGE, config=dict(endpoint)), ChainStep(kind=OAI, config=dict(endpoint))],
        ),
    })
    blob = IngestAssembler.assemble(state)
    assert validator.validate(builder.build(blob)) == []
    assert OnFailure in _edges(blob, "embed_0", "embed_1")
    assert ScoreBelow not in _edges(blob, "embed_0", "embed_1")
