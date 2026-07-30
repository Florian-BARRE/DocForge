"""The stage VIEW/READ layer: the default blob's canonical shape, the full 10-stage catalog,
and the compiler's dependency-cascade correctness (enrich requires render).

Sections 1, 2, 4a, 4b of the scratchpad's test_stage_layer.py — the only sections not already
covered elsewhere (5-8 are in test_providers.py/test_chains.py/test_stack.py; section 9, the
HTTP endpoints, belongs to tests/units/api/test_stage_endpoints.py). See
[[port-scratchpad-gap-plan]] and [[stage-combinatorics-strategy]].

Reuses the session-level ``builder``/``validator``/``compiler`` fixtures from
``tests/units/conftest.py`` — no local redefinition needed.
"""

from shared_libs.pipelines.base import FromNode
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import DisableStage, StageViewer, StateReader

EXPECTED_TOP_LEVEL_IDS = [
    "probe",
    "admit",
    "convert",
    "pdf_probe",
    "address",
    "parse",
    "figures",
    "extract",
    "per_figure",
    "apply",
    "chunk",
    "ctx_meta",
    "ctx_breadcrumb",
    "meta_chunk_prep",
    "meta_chunk_loop",
    "meta_chunk_apply",
    "meta_doc_prep",
    "meta_doc_loop",
    "meta_doc_apply",
    "embed",
    "bundle",
]

EXPECTED_STAGE_ORDER = [
    "intake",
    "parse",
    "render",
    "enrich",
    "chunk",
    "contextualize",
    "metagen_chunk",
    "metagen_document",
    "embed",
    "deliver",
]


def _view(blob, builder, validator):
    """Stage view of a blob, keyed by stage key (mirrors the scratchpad's ``view`` helper)."""
    return {stage.key: stage for stage in StageViewer.catalog(StateReader.read(blob)).stages}


def test_default_blob_has_the_canonical_top_level_node_ids_and_zero_issues(
    builder, validator
) -> None:
    default = IngestPipeline.default_blob()
    top_ids = [node.id for node in default.nodes]
    assert top_ids == EXPECTED_TOP_LEVEL_IDS
    issues = validator.validate(builder.build(default))
    assert issues == [], issues


def test_stage_catalog_lists_all_ten_stages_in_run_order_all_enabled(builder, validator) -> None:
    default = IngestPipeline.default_blob()
    keys = [stage.key for stage in StageViewer.catalog(StateReader.read(default)).stages]
    assert keys == EXPECTED_STAGE_ORDER
    stages = _view(default, builder, validator)
    assert all(stage.enabled for stage in stages.values()), "every stock stage enabled"


def test_stage_catalog_flags_removable_and_available_providers(builder, validator) -> None:
    default = IngestPipeline.default_blob()
    stages = _view(default, builder, validator)
    # Provider stages carry their kind + the family's choices.
    assert stages["chunk"].provider == "structure_aware"
    assert "fixed_size" in stages["chunk"].available
    assert stages["embed"].provider == "bge_server"
    assert stages["embed"].removable is True
    # Mandatory stages are never removable.
    assert stages["intake"].removable is False
    assert stages["parse"].removable is False


def test_disable_enrich_alone_rebinds_chunk_ir_to_render_with_no_render_notice(
    builder, validator, compiler
) -> None:
    """Disabling enrich (render stays on) must rebind chunk.ir to render's output, cleanly,
    and must NEVER mention render in its notices — the two toggles are independent here."""
    default = IngestPipeline.default_blob()
    off_enrich, enrich_notices = compiler.apply(default, DisableStage(stage="enrich"))

    issues = validator.validate(builder.build(off_enrich))
    assert issues == [], issues
    assert not any(n.id in ("extract", "per_figure", "apply") for n in off_enrich.nodes)
    assert off_enrich.bindings["chunk"]["ir"] == FromNode(node_id="figures", field_name="ir")
    assert _view(off_enrich, builder, validator)["enrich"].enabled is False
    assert not any("render" in note for note in enrich_notices), enrich_notices


def test_disable_render_cascades_enrich_off_with_a_notice_and_falls_back_to_parse(
    builder, validator, compiler
) -> None:
    """Disabling render must cascade-disable enrich (enrich `requires` render) — WITH a notice —
    and chunk.ir must fall all the way back to parse.ir; bundle.pages becomes unbound."""
    default = IngestPipeline.default_blob()
    off_render, render_notices = compiler.apply(default, DisableStage(stage="render"))

    issues = validator.validate(builder.build(off_render))
    assert issues == [], issues
    assert any("enrich" in note for note in render_notices), render_notices

    stages = _view(off_render, builder, validator)
    assert stages["enrich"].enabled is False
    assert stages["render"].enabled is False
    assert off_render.bindings["chunk"]["ir"] == FromNode(node_id="parse", field_name="ir")
    assert "pages" not in off_render.bindings["bundle"], "no render -> bundle.pages unbound"
