"""The design surface: zero mute field descriptions, connectability flags (scored/switch_fields),
family modes in the palette, lean-vs-full palette, and the default blob's stage coverage.

Ported from the scratchpad's test_design_surface.py. Sections 1-4 hit the pure pipeline layer
directly (no HTTP needed); one extra test confirms the ``?full=true`` query flows through the
real router (see [[port-scratchpad-gap-plan]]).
"""

from typing import Any, get_args

from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.edit.operations import EditOperation
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import EnableStage, StageAction, StageCompiler
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import GraphValidator


def _union_discriminator(alias: Any) -> str:
    """The tag field name of a `type X = Annotated[…, Field(discriminator=…)]` union, read from its
    own metadata — the source of truth the surfaced ``MechanicCard.discriminator`` must mirror."""
    return get_args(alias.__value__)[1].discriminator


def _union_tags(alias: Any, discriminator: str) -> set[str]:
    """The set of discriminator defaults of a `type X = Annotated[A | B | …]` union — the source
    of truth the introspection must mirror (add a variant and this set grows on its own)."""
    members = get_args(get_args(alias.__value__)[0])
    return {str(m.model_fields[discriminator].default) for m in members}


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
    # VLM is now a ScoreBelow source too (VlmProduces is a ScoredOutput) — auto-derived, not declared.
    assert NodeRegistry.get("vlm", "openai_compatible").describe().scored is True


def test_classifier_exposes_its_five_switch_values() -> None:
    described = NodeRegistry.get("enrich", "figure_classify").describe()
    assert described.scored is True
    assert set(described.switch_fields["kind"]) == {
        "photo",
        "scanned_text",
        "chart",
        "diagram",
        "decorative",
    }


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
        "always",
        "on_success",
        "on_failure",
        "score_below",
        "when_equals",
    }
    assert "DocumentIR" in full.artefacts
    assert full.artefacts["Chunk"].json_schema["properties"]


def test_full_mechanics_surfaces_the_edit_operation_vocabulary() -> None:
    """Every EditOperation variant is described with its tag + params_schema, dynamically matching
    the source union (add an operation and the introspection must grow with it — no frozen list)."""
    mechanics = IngestPipeline.palette(full=True).mechanics
    expected = _union_tags(EditOperation, "op")
    assert len(expected) == 9  # the 9 graph mutations documented in PIPELINE.md / architecture.md
    cards = {card.kind: card for card in mechanics.edit_operations}
    assert set(cards) == expected
    # The discriminator key a client sends this variant under is surfaced, dynamically matching the
    # source union's Field(discriminator=…) — a rename in the source flips this without touching here.
    op_key = _union_discriminator(EditOperation)
    assert op_key == "op"
    # Every card carries the params form the discriminator was stripped from (never the tag itself).
    for kind, card in cards.items():
        assert card.discriminator == op_key
        assert "properties" in card.params_schema
        assert op_key not in card.params_schema.get("properties", {})
        assert card.name and card.summary


def test_full_mechanics_surfaces_the_stage_action_vocabulary() -> None:
    """Every StageAction variant is described with its tag + params_schema, dynamically matching the
    source union — the ingest stage-rail vocabulary a client composes /stages/apply from."""
    mechanics = IngestPipeline.palette(full=True).mechanics
    expected = _union_tags(StageAction, "action")
    assert len(expected) == 6  # enable/disable/set_provider/set_config/set_chain/set_stack
    cards = {card.kind: card for card in mechanics.stage_actions}
    assert set(cards) == expected
    action_key = _union_discriminator(StageAction)
    assert action_key == "action"
    for kind, card in cards.items():
        assert card.discriminator == action_key
        assert "properties" in card.params_schema
        assert action_key not in card.params_schema.get("properties", {})
        assert card.name and card.summary


def test_search_mechanics_has_no_stage_actions_but_keeps_edit_operations() -> None:
    """Stage actions are ingest-only (the stage rail is ingest-coupled); the edit-operation
    vocabulary is pipeline-agnostic, so it surfaces for search too."""
    mechanics = SearchPipeline.palette(full=True).mechanics
    assert mechanics.stage_actions == []
    assert {card.kind for card in mechanics.edit_operations} == _union_tags(EditOperation, "op")


def test_full_query_flag_carries_the_mutation_vocabularies_through_the_router(client) -> None:
    """The new schemas must reach an MCP/SDK client through the real endpoint, not just in-process."""
    payload = client.get("/api/v1/pipelines/ingest", params={"full": "true"}).json()
    mechanics = payload["palette"]["mechanics"]
    assert {card["kind"] for card in mechanics["edit_operations"]} == _union_tags(
        EditOperation, "op"
    )
    assert {card["kind"] for card in mechanics["stage_actions"]} == _union_tags(
        StageAction, "action"
    )


def test_palette_hides_internal_kinds_but_keeps_them_registered() -> None:
    """Internal wiring nodes (prep/apply/skip terminals a stage builder emits) are SELECTABLE=False:
    the discovery palette never offers them as a stage method, yet they stay registered and
    describable for the graph engine."""
    palette = {
        family.family: {node.kind for node in family.nodes}
        for family in IngestPipeline.palette().families
    }
    internal = {
        "metagen": {"chunk_prep", "document_prep", "chunk_apply", "document_apply", "metagen_skip"},
        "contextualize": {"llm_apply", "keep_raw"},
    }
    for family, kinds in internal.items():
        # 1. Hidden from the palette's stage-method picker.
        assert palette[family].isdisjoint(kinds), (family, palette[family] & kinds)
        # 2. Still registered AND describable — the engine reaches them by (family, kind).
        for kind in kinds:
            described = NodeRegistry.get(family, kind).describe()
            assert described.selectable is False
            assert described.kind == kind


def test_selectable_defaults_true_for_a_user_facing_method() -> None:
    """A real stage method (a chunker) stays selectable — the palette offers it."""
    assert NodeRegistry.get("chunker", "structure_aware").describe().selectable is True


def test_default_blob_covers_all_stages_and_validates_clean() -> None:
    # The provider-hosted stages (enrich, both metagen scopes) ship OFF; enable them to exercise the
    # fully-populated topology this test covers.
    compiler = StageCompiler()
    blob = IngestPipeline.default_blob()
    for stage in ("enrich", "metagen_chunk", "metagen_document"):
        blob, _ = compiler.apply(blob, EnableStage(stage=stage))
    ids = [node.id for node in blob.nodes]
    for expected in (
        "probe",
        "parse",
        "per_figure",
        "chunk",
        "ctx_breadcrumb",
        "meta_chunk_prep",
        "meta_doc_apply",
        "embed",
        "bundle",
    ):
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
