"""Figure taxonomy single-source guard: FigureKind ⇄ FIGURE_ROUTING ⇄ enrich branches never drift.

FigureKind is the single source of the figure taxonomy. FIGURE_ROUTING hangs the routing off each
member; FIGURE_BRANCHES, DECORATIVE_KINDS and the classifier prompt all derive from it. These tests
lock the coupling so that adding a FigureKind without wiring its branch fails HERE (and at build),
never in production as a document that stalls on the classifier.
"""

import pytest

from shared_libs.pipelines.base import OnFailure, WhenEquals
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import EnableStage, FigureBranch, StageSpecs
from shared_libs.pipelines.ingest.stages.enrich_body import EnrichBodyBuilder
from shared_libs.public_models import FIGURE_ROUTING, FigureKind, figure_prompt_lines


def _enrich_body(blob):
    """The per-figure ForEach body of the default ingestion blob."""
    return next(node for node in blob.nodes if node.id == "per_figure").body


def test_routing_table_covers_every_figure_kind() -> None:
    """Every FigureKind carries routing — else the module import would already have failed."""
    assert set(FIGURE_ROUTING) == set(FigureKind)


def test_every_non_decorative_kind_has_exactly_one_branch() -> None:
    """The mandatory coupling: one FigureBranch per enriched class, decorative handled apart."""
    branches_by_kind: dict[str, list[FigureBranch]] = {}
    for branch in StageSpecs.FIGURE_BRANCHES:
        branches_by_kind.setdefault(branch.figure_kind, []).append(branch)

    for kind, routing in FIGURE_ROUTING.items():
        if routing.decorative:
            assert kind.value in StageSpecs.DECORATIVE_KINDS
            assert kind.value not in branches_by_kind
        else:
            assert len(branches_by_kind.get(kind.value, [])) == 1, kind


def test_branches_and_decoratives_partition_all_kinds() -> None:
    """Branch kinds and decorative kinds are disjoint and together cover every FigureKind."""
    branch_kinds = {branch.figure_kind for branch in StageSpecs.FIGURE_BRANCHES}
    assert branch_kinds.isdisjoint(StageSpecs.DECORATIVE_KINDS)
    assert branch_kinds | set(StageSpecs.DECORATIVE_KINDS) == {kind.value for kind in FigureKind}


def test_classifier_prompt_lists_every_kind() -> None:
    """The classifier prompt is derived from the table — one described line per FigureKind."""
    lines = figure_prompt_lines()
    for kind in FigureKind:
        assert f"- {kind.value}:" in lines


def test_default_enrich_body_routes_every_classifier_kind(compiler) -> None:
    """In the assembled default blob, every class the classifier can stamp has a when_equals edge.

    Enrich ships OFF by default (provider-hosted, opt-in), so enable it first to materialise the
    per-figure body this test inspects."""
    default, _ = compiler.apply(IngestPipeline.default_blob(), EnableStage(stage="enrich"))
    body = _enrich_body(default)
    classify = next(node for node in body.nodes if node.kind == "figure_classify")
    routed = {
        transition.condition.equals
        for transition in body.transitions
        if transition.from_node_id == classify.id and isinstance(transition.condition, WhenEquals)
    }
    assert routed == {kind.value for kind in FigureKind}


def test_every_chain_tail_fails_soft_to_the_classified_terminal(
    compiler, builder, validator
) -> None:
    """A figure whose WHOLE enrichment chain fails must pass through un-enriched, not sink the
    document: every chain's most-robust step (its tail — the one with no intra-chain on_failure
    fall-through left) carries an on_failure edge to the classified fail-soft terminal, which reads
    the CLASSIFIER's figure so the stamped kind (and any OCR read) survives the failure."""
    default, _ = compiler.apply(IngestPipeline.default_blob(), EnableStage(stage="enrich"))
    body = _enrich_body(default)

    on_failure = [t for t in body.transitions if isinstance(t.condition, OnFailure)]
    step_ids = {n.id for n in body.nodes if "_" in n.id and n.id.rsplit("_", 1)[1].isdigit()}
    # A tail is a chain step that never falls through to another chain step on failure.
    fails_to_step = {t.from_node_id for t in on_failure if t.to_node_id in step_ids}
    tails = step_ids - fails_to_step
    assert tails, "the default enrich chains must have provider steps"

    for tail in tails:
        assert any(
            t.from_node_id == tail and t.to_node_id == EnrichBodyBuilder.FAILSOFT_ID
            for t in on_failure
        ), f"chain tail '{tail}' has no fail-soft edge to the classified fail-soft terminal"

    # The classified fail-soft terminal reads the classifier's stamped figure (kind preserved), NOT
    # the raw ForEach item — that is the whole point of PIPELINE.md's "VLM KO → kind conservé".
    failsoft_binding = body.bindings[EnrichBodyBuilder.FAILSOFT_ID]["figure"]
    assert failsoft_binding.node_id == EnrichBodyBuilder.CLASSIFY_ID

    # The classifier is itself a VLM call — its OWN failure must still fall through to the skip
    # terminal (raw item), since a failed classify produced no figure to read the kind from.
    assert any(
        t.from_node_id == EnrichBodyBuilder.CLASSIFY_ID
        and t.to_node_id == EnrichBodyBuilder.SKIP_ID
        for t in on_failure
    ), "the classifier has no fail-soft edge to the skip terminal"

    # The fail-soft edges must not break the assembled graph.
    assert validator.validate(builder.build(default)) == []


def test_build_rejects_an_unrouted_classifier_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop a class's branch (the 'add FigureKind.MAP, wire nothing' drift): the BUILD must fail.

    The classifier can still stamp 'diagram', but nothing routes it — exactly what happens when a
    new FigureKind is added without a branch. The assembler rejects it at build, naming the class,
    instead of letting the item stall on 'classify' and fail the whole document at run.
    """
    surviving = tuple(b for b in StageSpecs.FIGURE_BRANCHES if b.figure_kind != "diagram")
    monkeypatch.setattr(StageSpecs, "FIGURE_BRANCHES", surviving)

    with pytest.raises(ValueError, match="diagram"):
        EnrichBodyBuilder.build(classify_config={}, chains={})
