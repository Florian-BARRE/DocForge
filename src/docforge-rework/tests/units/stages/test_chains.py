"""SetChain: every enrich slot x chain length (0/1/2/3 steps), config completion, invalid slot."""

import pytest

from shared_libs.pipelines.base import FromFirst
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import ChainStep, SetChain, StageSpecs, StateReader


def _body_of(blob):
    return next(n for n in blob.nodes if n.id == "per_figure").body


@pytest.mark.parametrize("branch", StageSpecs.FIGURE_BRANCHES, ids=lambda b: b.slot)
def test_single_step_chain_on_every_slot(compiler, builder, validator, branch) -> None:
    kind = "openai_compatible" if branch.family == "vlm" else "rapidocr"
    default = IngestPipeline.default_blob()
    chained, notices = compiler.apply(
        default, SetChain(stage="enrich", slot=branch.slot, steps=[ChainStep(kind=kind, config={})])
    )
    assert validator.validate(builder.build(chained)) == [], (branch.slot, notices)
    body = _body_of(chained)
    step_ids = [
        n.id for n in body.nodes
        if getattr(n, "family", None) == branch.family and n.id.startswith(f"{branch.slot}_")
    ]
    assert len(step_ids) == 1


@pytest.mark.parametrize("length", [1, 2, 3])
def test_ocr_chain_lengths(compiler, builder, validator, length) -> None:
    """The OCR family has two real kinds; a 3-step chain repeats one with a distinct config."""
    kinds = ["rapidocr", "mistral", "rapidocr"][:length]
    steps = [
        ChainStep(kind=k, config={"api_key": "SET_ME"} if k == "mistral" else {}, score_below=0.4 if i < length - 1 else None)
        for i, k in enumerate(kinds)
    ]
    default = IngestPipeline.default_blob()
    chained, notices = compiler.apply(default, SetChain(stage="enrich", slot="scanned_text_ocr", steps=steps))
    assert validator.validate(builder.build(chained)) == [], notices
    body = _body_of(chained)
    # Numbered steps only ("scanned_text_ocr_0", "_1", ...) — excludes the branch's terminal
    # "scanned_text_ocr_entry" node, which is not part of the chain itself.
    step_kinds = [
        n.kind for n in body.nodes
        if n.id.startswith("scanned_text_ocr_") and n.id.rsplit("_", 1)[-1].isdigit()
    ]
    assert step_kinds == kinds


def test_empty_chain_emits_a_notice_and_skips_the_class(compiler, builder, validator) -> None:
    default = IngestPipeline.default_blob()
    emptied, notices = compiler.apply(default, SetChain(stage="enrich", slot="photo_vlm", steps=[]))
    assert validator.validate(builder.build(emptied)) == []
    assert any("emptied" in n for n in notices)
    read_back = StateReader.read(emptied)
    assert "photo_vlm" not in read_back.chains


def test_chain_step_config_is_completed_build_safe(compiler) -> None:
    """A required field (e.g. mistral's api_key) missing from the step config becomes ''."""
    default = IngestPipeline.default_blob()
    chained, _ = compiler.apply(
        default, SetChain(stage="enrich", slot="scanned_text_ocr", steps=[ChainStep(kind="mistral", config={})])
    )
    body = _body_of(chained)
    mistral_step = next(n for n in body.nodes if n.kind == "mistral")
    assert mistral_step.config.get("api_key") == ""


def test_invalid_slot_is_a_clean_notice_not_an_exception(compiler) -> None:
    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(
        default, SetChain(stage="enrich", slot="does_not_exist", steps=[ChainStep(kind="rapidocr", config={})])
    )
    assert unchanged == default
    assert any("unknown chain slot" in n for n in notices)


def test_invalid_stage_for_set_chain_is_a_clean_notice(compiler) -> None:
    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(
        default, SetChain(stage="chunk", slot="scanned_text_ocr", steps=[ChainStep(kind="rapidocr", config={})])
    )
    assert unchanged == default
    assert notices


def test_set_chain_recompiles_from_first_best_first(compiler, builder, validator) -> None:
    default = IngestPipeline.default_blob()
    chained, _ = compiler.apply(
        default,
        SetChain(
            stage="enrich",
            slot="scanned_text_ocr",
            steps=[
                ChainStep(kind="rapidocr", config={}, score_below=0.4),
                ChainStep(kind="mistral", config={"api_key": "SET_ME"}),
            ],
        ),
    )
    assert validator.validate(builder.build(chained)) == []
    body = _body_of(chained)
    join = body.bindings["scanned_text_ocr_entry"]["figure"]
    assert isinstance(join, FromFirst)
    assert [c.node_id for c in join.candidates] == ["scanned_text_ocr_1", "scanned_text_ocr_0"]
