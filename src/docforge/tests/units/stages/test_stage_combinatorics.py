"""THE COMBINATORIAL HEART: every one of the 2^5 = 32 toggle combinations of the five optional
ingestion stages {render, enrich, metagen_chunk, metagen_document, embed}.

Each combo is built directly from a PipelineState (bypassing the compiler's dependency cascade,
which would collapse "enrich on / render off" back to a reachable state) — this is the strongest
form of the check: it proves the ASSEMBLER emits a buildable, 0-issue blob for literally any of
the 32 boolean vectors, not just the ones the compiler's cascade would ever produce on its own.
The cascade's own correctness (enabling enrich pulls render back, disabling render cascades
enrich off) is covered separately in test_view_reader.py.

For every combo we assert:
  1. the assembled blob builds and validates with ZERO issues,
  2. StateReader.read() round-trips the five toggles back exactly (reader/assembler agree),
  3. re-assembling the read-back state reproduces an identical stage view (idempotent),
  4. the IR spine (chunk.ir) and the bundle's optional slots are wired to the RIGHT producer
     for that combo (a spot-check of the rebinding rules, not just "no issues").
"""

import itertools

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest.stages import (
    ChainSpec,
    IngestAssembler,
    StageViewer,
    StateReader,
    default_state,
)
from shared_libs.pipelines.ingest.stages.models import ChainStep
from shared_libs.pipelines.validation import GraphValidator

TOGGLE_FIELDS = ("render_on", "enrich_on", "metachunk_on", "metadoc_on", "embed_on")

# All 32 boolean vectors over the 5 independent toggles, in a stable, readable order.
ALL_32_COMBOS = list(itertools.product([False, True], repeat=len(TOGGLE_FIELDS)))


def _combo_id(combo: tuple[bool, ...]) -> str:
    flags = "".join(
        f"{name.replace('_on', '')}={int(value)},"
        for name, value in zip(TOGGLE_FIELDS, combo, strict=True)
    )
    return flags.rstrip(",")


@pytest.fixture(scope="module")
def builder() -> PipelineBuilder:
    return PipelineBuilder()


@pytest.fixture(scope="module")
def validator() -> GraphValidator:
    return GraphValidator()


@pytest.mark.parametrize("combo", ALL_32_COMBOS, ids=[_combo_id(c) for c in ALL_32_COMBOS])
def test_every_toggle_combination_builds_and_validates_clean(builder, validator, combo) -> None:
    overrides = dict(zip(TOGGLE_FIELDS, combo, strict=True))
    state = default_state().model_copy(update=overrides)

    blob = IngestAssembler.assemble(state)
    group = builder.build(blob)
    issues = validator.validate(group)
    assert issues == [], (overrides, issues)


@pytest.mark.parametrize("combo", ALL_32_COMBOS, ids=[_combo_id(c) for c in ALL_32_COMBOS])
def test_every_combination_reader_round_trips_the_five_toggles(combo) -> None:
    overrides = dict(zip(TOGGLE_FIELDS, combo, strict=True))
    state = default_state().model_copy(update=overrides)
    blob = IngestAssembler.assemble(state)

    read_back = StateReader.read(blob)
    for field in TOGGLE_FIELDS:
        assert getattr(read_back, field) == overrides[field], field


@pytest.mark.parametrize("combo", ALL_32_COMBOS, ids=[_combo_id(c) for c in ALL_32_COMBOS])
def test_every_combination_view_is_idempotent_on_reassembly(combo) -> None:
    """view(assemble(read(assemble(state)))) == view(assemble(state)) — no drift on a second pass."""
    overrides = dict(zip(TOGGLE_FIELDS, combo, strict=True))
    state = default_state().model_copy(update=overrides)
    blob = IngestAssembler.assemble(state)

    reread_state = StateReader.read(blob)
    rebuilt_blob = IngestAssembler.assemble(reread_state)

    original_view = StageViewer.catalog(StateReader.read(blob)).stages
    rebuilt_view = StageViewer.catalog(StateReader.read(rebuilt_blob)).stages
    assert [(s.key, s.enabled, s.provider) for s in original_view] == [
        (s.key, s.enabled, s.provider) for s in rebuilt_view
    ]


@pytest.mark.parametrize("combo", ALL_32_COMBOS, ids=[_combo_id(c) for c in ALL_32_COMBOS])
def test_every_combination_rebindings_match_the_toggle_state(combo) -> None:
    """Spot-check the spine rebinding rules that make the assembler's output actually coherent."""
    render_on, enrich_on, metachunk_on, metadoc_on, embed_on = combo
    overrides = dict(zip(TOGGLE_FIELDS, combo, strict=True))
    state = default_state().model_copy(update=overrides)
    blob = IngestAssembler.assemble(state)
    bindings = blob.bindings

    # 1. chunk.ir reads the nearest enabled producer of the IR spine: apply (enrich) > figures
    #    (render) > parse.
    expected_ir_source = "apply" if enrich_on else ("figures" if render_on else "parse")
    assert bindings["chunk"]["ir"].node_id == expected_ir_source, combo

    # 2. bundle.pages exists iff render is on.
    assert ("pages" in bindings["bundle"]) == render_on, combo

    # 3. bundle.document_meta exists iff metagen_document is on, and reads the document apply node.
    assert ("document_meta" in bindings["bundle"]) == metadoc_on, combo
    if metadoc_on:
        assert bindings["bundle"]["document_meta"].node_id == "meta_doc_apply"

    # 4. bundle.embeddings exists iff embed is on, and reads embed.
    assert ("embeddings" in bindings["bundle"]) == embed_on, combo
    if embed_on:
        assert bindings["bundle"]["embeddings"].node_id == "embed"

    # 5. the metagen prep/loop/apply, embed and render/enrich nodes are present iff their toggle is on.
    node_ids = {n.id for n in blob.nodes}
    assert ("meta_chunk_prep" in node_ids) == metachunk_on, combo
    assert ("meta_chunk_loop" in node_ids) == metachunk_on, combo
    assert ("meta_chunk_apply" in node_ids) == metachunk_on, combo
    assert ("meta_doc_prep" in node_ids) == metadoc_on, combo
    assert ("meta_doc_apply" in node_ids) == metadoc_on, combo
    assert ("embed" in node_ids) == embed_on, combo
    assert ("figures" in node_ids) == render_on, combo
    assert ("per_figure" in node_ids) == enrich_on, combo


def test_two_step_metagen_chain_round_trips_and_is_idempotent() -> None:
    """A 2-step structgen ladder on both metagen scopes survives compile → read → compile.

    The multi-loop reader must disambiguate the two metagen loops from the enrich loop AND from
    each other (by the prep the loop's ``over`` reads), then walk each structgen ladder back — so
    a non-default chain is not silently collapsed to the stock 1-step default.
    """
    ladder = ChainSpec(
        family="structgen",
        steps=[
            ChainStep(
                kind="openai_compatible", config={"base_url": "http://cheap", "model": "small"}
            ),
            ChainStep(
                kind="openai_compatible", config={"base_url": "http://robust", "model": "big"}
            ),
        ],
    )
    state = default_state().model_copy(
        update={
            "metachunk_on": True,
            "metadoc_on": True,
            "metachunk_chain": ladder.model_copy(deep=True),
            "metadoc_chain": ladder.model_copy(deep=True),
        }
    )

    blob = IngestAssembler.assemble(state)
    assert GraphValidator().validate(PipelineBuilder().build(blob)) == []

    read_back = StateReader.read(blob)
    assert [s.kind for s in read_back.metachunk_chain.steps] == [
        "openai_compatible",
        "openai_compatible",
    ]
    assert read_back.metachunk_chain.steps[1].config == {
        "base_url": "http://robust",
        "model": "big",
    }
    assert [s.kind for s in read_back.metadoc_chain.steps] == [
        "openai_compatible",
        "openai_compatible",
    ]

    # compile → read → compile is a fixed point: re-assembling the read-back state is byte-identical.
    assert IngestAssembler.assemble(read_back).model_dump(mode="json") == blob.model_dump(
        mode="json"
    )
