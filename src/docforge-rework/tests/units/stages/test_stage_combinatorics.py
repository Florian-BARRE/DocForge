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
    IngestAssembler,
    StageViewer,
    StateReader,
    default_state,
)
from shared_libs.pipelines.validation import GraphValidator

TOGGLE_FIELDS = ("render_on", "enrich_on", "metachunk_on", "metadoc_on", "embed_on")

# All 32 boolean vectors over the 5 independent toggles, in a stable, readable order.
ALL_32_COMBOS = list(itertools.product([False, True], repeat=len(TOGGLE_FIELDS)))


def _combo_id(combo: tuple[bool, ...]) -> str:
    flags = "".join(f"{name.replace('_on', '')}={int(value)}," for name, value in zip(TOGGLE_FIELDS, combo, strict=True))
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

    # 3. bundle.document_meta exists iff metagen_document is on, and reads meta_doc.
    assert ("document_meta" in bindings["bundle"]) == metadoc_on, combo
    if metadoc_on:
        assert bindings["bundle"]["document_meta"].node_id == "meta_doc"

    # 4. bundle.embeddings exists iff embed is on, and reads embed.
    assert ("embeddings" in bindings["bundle"]) == embed_on, combo
    if embed_on:
        assert bindings["bundle"]["embeddings"].node_id == "embed"

    # 5. meta_chunk/meta_doc/embed nodes are present in the node list iff their toggle is on.
    node_ids = {n.id for n in blob.nodes}
    assert ("meta_chunk" in node_ids) == metachunk_on, combo
    assert ("meta_doc" in node_ids) == metadoc_on, combo
    assert ("embed" in node_ids) == embed_on, combo
    assert ("figures" in node_ids) == render_on, combo
    assert ("per_figure" in node_ids) == enrich_on, combo
