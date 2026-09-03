"""The enrich topology mode (`figure_enrich_mode`): classified (stock) vs uniform (one treatment).

Proves the bodies the enrich ForEach compiles to:
  * classified (default) is UNCHANGED — a classifier drives a per-class WhenEquals switch;
  * uniform drops the classifier + switch entirely — every figure runs ONE treatment and closes on a
    model-free terminal, with an OnFailure fail-soft so an un-enriched figure still passes:
      - treatment ``ocr`` → a local OCR chain closing on figure_entry;
      - treatment ``vlm`` → a vision-model chain (describe, configurable prompt) closing on vlm_entry.
Both must pass GraphValidator, and the mode/treatment must round-trip through the stage view/compile.
The pre-0.12 ``ocr_only`` mode value is still accepted (normalised to uniform).

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


def _enable_uniform(compiler, treatment="ocr", mode="uniform"):
    """Enable enrich, then flip it to uniform (with a treatment) via the enrich stage config."""
    on, _ = compiler.apply(IngestPipeline.default_blob(), EnableStage(stage="enrich"))
    # The enrich stage config carries the topology selectors; the studio POSTs them back on set_config.
    config = {
        **_enrich_view(on).config,
        "figure_enrich_mode": mode,
        "uniform_treatment": treatment,
    }
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


def test_uniform_ocr_body_has_no_classifier_and_no_switch(compiler, builder, validator) -> None:
    """uniform+ocr drops the classifier + switch — item -> local OCR chain -> figure_entry, fail-soft."""
    blob, notices = _enable_uniform(compiler, treatment="ocr")

    # 1. The whole graph still builds and validates cleanly.
    assert validator.validate(builder.build(blob)) == [], notices

    body = _body_of(blob)
    kinds = [n.kind for n in body.nodes]
    # 2. No classifier, no WhenEquals switch anywhere in the body.
    assert "figure_classify" not in kinds
    assert not any(isinstance(t.condition, WhenEquals) for t in body.transitions)
    # 3. A local OCR chain closes on a model-free figure_entry — its HEAD is the local rapidocr.
    ocr_steps = [n for n in body.nodes if getattr(n, "family", None) == "ocr"]
    assert ocr_steps and ocr_steps[0].kind == "rapidocr"
    assert any(n.kind == "figure_entry" for n in body.nodes)
    # 4. Every step exits OnSuccess to the success terminal.
    success = [t for t in body.transitions if isinstance(t.condition, OnSuccess)]
    assert success and all(t.to_node_id == "uniform_entry" for t in success)
    # 5. Fail-soft: the chain tail routes OnFailure to the skip terminal (raw figure passes through).
    failsoft = [t for t in body.transitions if isinstance(t.condition, OnFailure)]
    assert any(t.to_node_id == "entry" for t in failsoft)


def test_uniform_vlm_body_describes_every_figure(compiler, builder, validator) -> None:
    """uniform+vlm runs a vision-model chain on every figure — no OCR, closes on vlm_entry."""
    blob, notices = _enable_uniform(compiler, treatment="vlm")

    assert validator.validate(builder.build(blob)) == [], notices
    body = _body_of(blob)
    # No classifier, no OCR — a VLM chain drives every figure.
    assert "figure_classify" not in [n.kind for n in body.nodes]
    assert not any(getattr(n, "family", None) == "ocr" for n in body.nodes)
    vlm_steps = [n for n in body.nodes if getattr(n, "family", None) == "vlm"]
    assert vlm_steps and vlm_steps[0].kind == "openai_compatible"
    # Closes on a model-free vlm_entry (the describe terminal), with the same fail-soft skip.
    assert any(n.kind == "vlm_entry" for n in body.nodes)
    assert any(
        isinstance(t.condition, OnFailure) and t.to_node_id == "entry" for t in body.transitions
    )
    # Round-trips: mode uniform + treatment vlm, chain into the figure_describe_vlm slot.
    state = StateReader.read(blob)
    assert state.figure_enrich_mode == "uniform" and state.uniform_treatment == "vlm"
    assert "figure_describe_vlm" in state.chains


def test_uniform_mode_round_trips_through_view(compiler, builder, validator) -> None:
    """uniform mode/treatment are derived from topology on read and surfaced on the enrich config."""
    blob, _ = _enable_uniform(compiler, treatment="ocr")
    state = StateReader.read(blob)
    assert state.figure_enrich_mode == "uniform" and state.uniform_treatment == "ocr"
    assert "scanned_text_ocr" in state.chains
    enrich_view = next(s for s in StageViewer.catalog(state).stages if s.key == "enrich")
    assert enrich_view.config.get("figure_enrich_mode") == "uniform"
    assert enrich_view.config.get("uniform_treatment") == "ocr"


def test_legacy_ocr_only_value_normalises_to_uniform(compiler, builder, validator) -> None:
    """The pre-0.12 ``ocr_only`` mode value is accepted and normalised to uniform (ocr treatment)."""
    blob, notices = _enable_uniform(compiler, treatment="ocr", mode="ocr_only")
    assert validator.validate(builder.build(blob)) == [], notices
    assert StateReader.read(blob).figure_enrich_mode == "uniform"


def test_uniform_ocr_survives_a_multi_step_chain(compiler, builder, validator) -> None:
    """A rapidocr -> mistral escalation chain still compiles in uniform+ocr (best-first convergence)."""
    from shared_libs.pipelines.ingest.stages import ChainStep, SetChain

    blob, _ = _enable_uniform(compiler, treatment="ocr")
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
        if n.id.startswith("figure_uniform_") and n.id.rsplit("_", 1)[-1].isdigit()
    ]
    assert ocr_kinds == ["rapidocr", "mistral"]
