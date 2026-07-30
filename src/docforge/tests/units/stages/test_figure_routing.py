"""Figure taxonomy single-source guard: FigureKind ⇄ FIGURE_ROUTING ⇄ enrich branches never drift.

FigureKind is the single source of the figure taxonomy. FIGURE_ROUTING hangs the routing off each
member; FIGURE_BRANCHES, DECORATIVE_KINDS and the classifier prompt all derive from it. These tests
lock the coupling so that adding a FigureKind without wiring its branch fails HERE (and at build),
never in production as a document that stalls on the classifier.
"""

import pytest

from shared_libs.pipelines.base import WhenEquals
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
