"""The design surface: zero mute field descriptions, connectability flags (scored/switch_fields),
family modes in the palette, lean-vs-full palette, and the default blob's stage coverage.

Ported from the scratchpad's test_design_surface.py. Sections 1-4 hit the pure pipeline layer
directly (no HTTP needed); one extra test confirms the ``?full=true`` query flows through the
real router (see [[port-scratchpad-gap-plan]]).
"""

from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry
from shared_libs.pipelines.validation import GraphValidator


def test_every_registered_node_has_zero_mute_field_descriptions() -> None:
    """Every Config/Consumes/Produces field must carry a Field(description=...) — the UI has no
    hardcoded copy, it renders whatever the backend describes.

    Skips ``test_``-prefixed kinds: other test modules in this session register throwaway fake
    nodes under real families (e.g. "deliver") without bothering with descriptions — see
    [[noderegistry-global-state]]. No REAL node kind is ever prefixed "test_".
    """
    missing = []
    for family in NodeRegistry.families():
        for kind in NodeRegistry.kinds(family):
            if kind.startswith("test_") or kind.startswith("fake_"):
                continue
            node_class = NodeRegistry.get(family, kind)
            if not issubclass(node_class, ActionNode):
                continue
            for field_name, field_info in node_class.Config.model_fields.items():
                if not field_info.description:
                    missing.append(f"{family}/{kind}.config.{field_name}")
            for face in ("Consumes", "Produces"):
                for field_name, field_info in getattr(node_class, face).model_fields.items():
                    if not field_info.description:
                        missing.append(f"{family}/{kind}.{face}.{field_name}")
    assert not missing, missing


def test_describe_forwards_every_io_slot_description() -> None:
    described = NodeRegistry.get("chunker", "structure_aware").describe()
    assert all(slot.description for slot in described.consumes + described.produces)


def test_scored_flag_is_auto_derived_from_the_output_face() -> None:
    assert NodeRegistry.get("ocr", "rapidocr").describe().scored is True  # ScoreBelow source
    assert NodeRegistry.get("vlm", "openai_compatible").describe().scored is False


def test_classifier_exposes_its_five_switch_values() -> None:
    described = NodeRegistry.get("enrich", "figure_classify").describe()
    assert described.scored is True
    assert set(described.switch_fields["kind"]) == {"photo", "scanned_text", "chart", "diagram", "decorative"}


def test_palette_family_modes_match_the_ui_interaction_style() -> None:
    palette = IngestPipeline.palette()
    modes = {family.family: family.mode for family in palette.families}
    assert modes["chunker"] == FamilyMode.EXCLUSIVE
    assert modes["contextualize"] == FamilyMode.STACKABLE
    assert modes["ocr"] == FamilyMode.CHAIN
    assert modes["intake"] == FamilyMode.STAGE
    assert modes["deliver"] == FamilyMode.STAGE
    assert all(family.title and family.description for family in palette.families)


def test_default_palette_is_lean_advanced_blocks_stay_none() -> None:
    palette = IngestPipeline.palette()
    assert palette.run_inputs is None
    assert palette.mechanics is None
    assert palette.artefacts is None


def test_full_palette_carries_run_inputs_mechanics_and_artefacts() -> None:
    full = IngestPipeline.palette(full=True)
    assert [slot.name for slot in full.run_inputs] == ["source", "contract"]
    assert {condition.kind for condition in full.mechanics.conditions} == {
        "always", "on_success", "on_failure", "score_below", "when_equals",
    }
    assert "DocumentIR" in full.artefacts
    assert full.artefacts["Chunk"].json_schema["properties"]


def test_default_blob_covers_all_stages_and_validates_clean() -> None:
    blob = IngestPipeline.default_blob()
    ids = [node.id for node in blob.nodes]
    for expected in ("probe", "parse", "per_figure", "chunk", "ctx_breadcrumb", "meta_chunk", "meta_doc", "embed", "bundle"):
        assert expected in ids, expected
    issues = GraphValidator().validate(PipelineBuilder().build(blob))
    assert issues == [], issues


def test_full_query_flag_flows_through_the_router(client) -> None:
    lean = client.get("/api/v1/pipelines/ingest")
    assert lean.status_code == 200, lean.text
    assert lean.json()["palette"]["run_inputs"] is None

    full = client.get("/api/v1/pipelines/ingest", params={"full": "true"})
    assert full.status_code == 200, full.text
    assert full.json()["palette"]["run_inputs"] is not None
