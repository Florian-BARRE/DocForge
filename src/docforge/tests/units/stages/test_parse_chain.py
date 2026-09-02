"""Parse as a scored fallback chain (docling → a stronger parser): a >1-step parse chain
build/validates with 0 issues, wires ScoreBelow + OnFailure escalation with a best-first join,
and round-trips through the reader; SetProvider(parse) stays 1-step sugar; the compiler surfaces
the required-empty and duplicate-unique chain rules as notices.

Registers a FAKE second parser kind under family ``parser`` (only ``docling`` is real), mirroring
``tests/units/nodes/test_embed_stage.py::FakeEmbed`` — the registration is process-global, so the
fake also shows up in NodeRegistry.kinds("parser") for the shared provider tests (harmless: a valid
1-step parser builds cleanly).
"""

from shared_libs.pipelines.base import (
    FromFirst,
    FromNode,
    NodeConfig,
    OnFailure,
    OnSuccess,
    ScoreBelow,
)
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.stages import (
    ChainSpec,
    ChainStep,
    IngestAssembler,
    SetChain,
    SetProvider,
    SetStageConfig,
    StateReader,
    default_state,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR, IntakeResult

FAKE_KIND = "test_parser_fake_strong"


class FakeParserConfig(NodeConfig):
    """No knobs — the fake parser exists only to give the chain a second, non-docling step."""


@NodeRegistry.register("parser")
class FakeStrongParser(BaseParserNode):
    """A stub second parser so a real >1-step parse chain can be exercised (docling is unique)."""

    KIND = FAKE_KIND
    NAME = "Fake strong parser"
    SUMMARY = "A stub stronger parser used only in tests."
    Config = FakeParserConfig

    async def _parse(self, pdf_bytes: bytes, source: IntakeResult) -> DocumentIR:
        return DocumentIR(doc_id=source.source_hash, source_hash=source.source_hash)


def _two_step_chain(compiler):
    """Compile the default blob with a docling → fake 2-step parse chain (score_below on step 0)."""
    default = IngestPipeline.default_blob()
    return compiler.apply(
        default,
        SetChain(
            stage="parse",
            slot=None,
            steps=[ChainStep(kind="docling", score_below=0.5), ChainStep(kind=FAKE_KIND)],
        ),
    )


def _edges(blob, from_id, to_id):
    """The transition conditions on every edge from_id → to_id in the top-level blob."""
    return [
        type(t.condition)
        for t in blob.transitions
        if t.from_node_id == from_id and t.to_node_id == to_id
    ]


def test_two_step_parse_chain_builds_and_validates(compiler, builder, validator) -> None:
    chained, notices = _two_step_chain(compiler)
    assert validator.validate(builder.build(chained)) == [], notices


def test_two_step_parse_chain_wires_escalation_and_best_first_join(builder, validator) -> None:
    # A minimal pipeline (render + enrich off) so the parse chain feeds the chunk head DIRECTLY —
    # the clearest view of the escalation topology and the convergence anchor.
    state = default_state().model_copy(
        update={
            "render_on": False,
            "enrich_on": False,
            "parse_chain": ChainSpec(
                family="parser",
                steps=[ChainStep(kind="docling", score_below=0.5), ChainStep(kind=FAKE_KIND)],
            ),
        }
    )
    blob = IngestAssembler.assemble(state)
    assert validator.validate(builder.build(blob)) == []

    node_ids = {n.id for n in blob.nodes}
    assert {"parse_0", "parse_1"} <= node_ids and "parse" not in node_ids

    # 1. Step 0 escalates to step 1 on low score AND falls through on failure.
    escalation = _edges(blob, "parse_0", "parse_1")
    assert ScoreBelow in escalation and OnFailure in escalation
    threshold = next(
        t.condition.threshold
        for t in blob.transitions
        if t.from_node_id == "parse_0" and isinstance(t.condition, ScoreBelow)
    )
    assert threshold == 0.5

    # 2. Either step, on success, exits to the chunk head.
    assert OnSuccess in _edges(blob, "parse_0", "chunk")
    assert OnSuccess in _edges(blob, "parse_1", "chunk")

    # 3. chunk.ir reads whichever parser answered — best (last) first.
    join = blob.bindings["chunk"]["ir"]
    assert isinstance(join, FromFirst)
    assert [c.node_id for c in join.candidates] == ["parse_1", "parse_0"]


def test_reader_round_trips_the_parse_chain(compiler) -> None:
    chained, _ = _two_step_chain(compiler)
    state = StateReader.read(chained)
    assert state.parse_chain.family == "parser"
    assert [s.kind for s in state.parse_chain.steps] == ["docling", FAKE_KIND]
    assert state.parse_chain.steps[0].score_below == 0.5
    assert state.parse_chain.steps[1].score_below is None


def test_docling_then_granite_escalation_chain_builds_and_validates(
    compiler, builder, validator
) -> None:
    """The real granite_docling kind wires as a ScoreBelow escalation step after docling and passes
    validation — proving the brick drops into a parser chain with zero engine change."""
    default = IngestPipeline.default_blob()
    chained, notices = compiler.apply(
        default,
        SetChain(
            stage="parse",
            slot=None,
            steps=[
                ChainStep(kind="docling", score_below=0.6),
                ChainStep(kind="granite_docling"),
            ],
        ),
    )
    assert validator.validate(builder.build(chained)) == [], notices
    state = StateReader.read(chained)
    assert [s.kind for s in state.parse_chain.steps] == ["docling", "granite_docling"]
    assert state.parse_chain.steps[0].score_below == 0.6


def test_docling_then_pp_structure_escalation_defaults_base_url_to_sidecar(
    compiler, builder, validator
) -> None:
    """A ``docling → ScoreBelow(0.30) → pp_structure`` chain builds/validates AND the added
    pp_structure step resolves its base_url to the in-stack sidecar (default), so an escalation
    added to a collection is reachable out of the box instead of pointing at an empty endpoint."""
    default = IngestPipeline.default_blob()
    chained, notices = compiler.apply(
        default,
        SetChain(
            stage="parse",
            slot=None,
            steps=[
                ChainStep(kind="docling", score_below=0.30),
                ChainStep(kind="pp_structure"),
            ],
        ),
    )
    # 1. The escalation chain builds and validates with zero structural issues.
    assert validator.validate(builder.build(chained)) == [], notices

    # 2. The pp_structure step's config resolves base_url to the in-stack sidecar (non-empty),
    #    because base_url now carries a default and is no longer a required-empty field.
    step = next(
        s for s in StateReader.read(chained).parse_chain.steps if s.kind == "pp_structure"
    )
    resolved = NodeRegistry.get("parser", "pp_structure").Config.model_validate(step.config)
    assert resolved.base_url == "http://paddle_server:80"

    # 3. No "missing endpoint" placeholder notice was raised for the reachable-by-default step.
    assert not any("no endpoint" in n for n in notices)


def test_empty_base_url_on_enabled_network_node_is_flagged(compiler) -> None:
    """Blanking an enabled network node's endpoint surfaces a notice at edit time (the guard),
    instead of building cleanly and only failing at the first spend."""
    default = IngestPipeline.default_blob()
    _, notices = compiler.apply(
        default,
        SetStageConfig(stage="intake", node="convert", config={"base_url": ""}),
    )
    assert any("no endpoint" in n for n in notices)


def test_set_provider_parse_is_one_step_chain_sugar(compiler) -> None:
    default = IngestPipeline.default_blob()
    swapped, _ = compiler.apply(default, SetProvider(stage="parse", kind="docling"))
    state = StateReader.read(swapped)
    assert len(state.parse_chain.steps) == 1
    assert state.parse_chain.steps[0].kind == "docling"
    # A single provider stays the stock lone 'parse' node with a plain FromNode anchor (render is
    # on in the default, so the parse anchor surfaces on figures.ir).
    assert any(n.id == "parse" for n in swapped.nodes)
    assert swapped.bindings["figures"]["ir"] == FromNode(node_id="parse", field_name="ir")


def test_empty_parse_chain_is_kept_with_a_required_notice(compiler) -> None:
    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(default, SetChain(stage="parse", slot=None, steps=[]))
    assert any("at least one provider" in n for n in notices)
    # The required stage keeps its current (docling) chain — never emptied.
    assert StateReader.read(unchanged).parse_chain.steps[0].kind == "docling"


def test_duplicate_unique_parser_in_chain_is_a_notice(compiler) -> None:
    default = IngestPipeline.default_blob()
    _, notices = compiler.apply(
        default,
        SetChain(
            stage="parse",
            slot=None,
            steps=[ChainStep(kind="docling", score_below=0.5), ChainStep(kind="docling")],
        ),
    )
    assert any("only once" in n for n in notices)


def test_set_provider_parse_unknown_kind_is_a_notice_not_an_exception(compiler) -> None:
    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(default, SetProvider(stage="parse", kind="bogus"))
    assert unchanged == default
    assert any("'bogus' is not a 'parser' provider" in n for n in notices)


def test_set_chain_parse_unknown_step_kind_is_a_notice_not_an_exception(compiler) -> None:
    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(
        default,
        SetChain(
            stage="parse",
            slot=None,
            steps=[ChainStep(kind="docling", score_below=0.5), ChainStep(kind="bogus")],
        ),
    )
    assert unchanged == default
    assert any("'bogus' is not a 'parser' provider" in n for n in notices)
