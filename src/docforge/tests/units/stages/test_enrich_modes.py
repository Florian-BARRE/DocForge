"""B1 — the enrich topology mode (`figure_enrich_mode`): classified (stock) vs ocr_only.

Proves the two bodies the enrich ForEach compiles to:
  * classified (default) is UNCHANGED — a classifier drives a per-class WhenEquals switch;
  * ocr_only drops the classifier + switch entirely — every figure runs one local OCR chain and
    closes on a figure_entry, with an OnFailure fail-soft so an un-OCR'd figure still passes.
Both must pass GraphValidator, and the mode must round-trip through the stage view/compile.

Reuses the session-level ``builder``/``validator``/``compiler`` fixtures from tests/units/conftest.py.
"""

from shared_libs.pipelines.base import OnFailure, OnSuccess, WhenEquals
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import (
    EnableStage,
    SetStageConfig,
    StageViewer,
    StateReader,
)


def _body_of(blob):
    """The per-figure ForEach body of an assembled ingest blob."""
    return next(n for n in blob.nodes if n.id == "per_figure").body


def _enrich_view(blob):
    """The enrich stage view of a blob."""
    return next(s for s in StageViewer.catalog(StateReader.read(blob)).stages if s.key == "enrich")


def _enable_ocr_only(compiler):
    """Enable enrich, then flip it to ocr_only via the enrich stage config (as the studio would)."""
    on, _ = compiler.apply(IngestPipeline.default_blob(), EnableStage(stage="enrich"))
    # The enrich stage config carries the topology selector; the studio POSTs it back on set_config.
    config = {**_enrich_view(on).config, "figure_enrich_mode": "ocr_only"}
    return compiler.apply(on, SetStageConfig(stage="enrich", config=config))


def test_default_classified_body_is_unchanged(compiler, builder, validator) -> None:
    """The DEFAULT (classified) enrich body still classifies then switches per class."""
    on, _ = compiler.apply(IngestPipeline.default_blob(), EnableStage(stage="enrich"))
    assert validator.validate(builder.build(on)) == []
    body = _body_of(on)
    kinds = {n.id: n.kind for n in body.nodes}
    assert kinds.get("classify") == "figure_classify"
    switches = [t for t in body.transitions if isinstance(t.condition, WhenEquals)]
    assert switches, "classified mode must keep the per-class WhenEquals switch"
    # The mode round-trips as classified straight off the stock topology.
    assert StateReader.read(on).figure_enrich_mode == "classified"


def test_ocr_only_body_has_no_classifier_and_no_switch(compiler, builder, validator) -> None:
    """ocr_only drops the classifier + switch — item -> local OCR chain -> figure_entry, fail-soft."""
    blob, notices = _enable_ocr_only(compiler)

    # 1. The whole graph still builds and validates cleanly.
    assert validator.validate(builder.build(blob)) == [], notices

    body = _body_of(blob)
    kinds = [n.kind for n in body.nodes]
    # 2. No classifier, no WhenEquals switch anywhere in the body.
    assert "figure_classify" not in kinds
    assert not any(isinstance(t.condition, WhenEquals) for t in body.transitions)
    # 3. A local OCR chain closes on a model-free figure_entry — its HEAD is the local rapidocr
    #    (the reused scanned_text_ocr chain leads local; escalation is the user's opt-in).
    ocr_steps = [n for n in body.nodes if getattr(n, "family", None) == "ocr"]
    assert ocr_steps and ocr_steps[0].kind == "rapidocr"
    assert any(n.kind == "figure_entry" for n in body.nodes)
    # 4. Every OCR step exits OnSuccess to the success terminal.
    success = [t for t in body.transitions if isinstance(t.condition, OnSuccess)]
    assert success and all(t.to_node_id == "ocr_entry" for t in success)
    # 5. Fail-soft: the chain tail routes OnFailure to the skip terminal (raw figure passes through).
    failsoft = [t for t in body.transitions if isinstance(t.condition, OnFailure)]
    assert any(t.to_node_id == "entry" for t in failsoft)


def test_ocr_only_mode_round_trips_through_view(compiler, builder, validator) -> None:
    """The ocr_only mode is derived from topology on read and surfaced on the enrich stage config."""
    blob, _ = _enable_ocr_only(compiler)
    state = StateReader.read(blob)
    assert state.figure_enrich_mode == "ocr_only"
    # The single OCR chain round-trips into the scanned_text_ocr slot.
    assert "scanned_text_ocr" in state.chains
    # The stage view surfaces the mode on the enrich config so the studio re-renders the selector.
    enrich_view = next(s for s in StageViewer.catalog(state).stages if s.key == "enrich")
    assert enrich_view.config.get("figure_enrich_mode") == "ocr_only"


def test_ocr_only_survives_a_multi_step_ocr_chain(compiler, builder, validator) -> None:
    """A rapidocr -> mistral escalation chain still compiles in ocr_only (best-first convergence)."""
    from shared_libs.pipelines.ingest.stages import ChainStep, SetChain

    blob, _ = _enable_ocr_only(compiler)
    chained, notices = compiler.apply(
        blob,
        SetChain(
            stage="enrich",
            slot="scanned_text_ocr",
            steps=[
                ChainStep(kind="rapidocr", config={}, score_below=0.4),
                ChainStep(kind="mistral", config={"api_key": "SET_ME"}),
            ],
        ),
    )
    assert validator.validate(builder.build(chained)) == [], notices
    body = _body_of(chained)
    ocr_kinds = [
        n.kind
        for n in body.nodes
        if n.id.startswith("figure_ocr_") and n.id.rsplit("_", 1)[-1].isdigit()
    ]
    assert ocr_kinds == ["rapidocr", "mistral"]
