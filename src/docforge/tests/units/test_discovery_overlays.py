# ====== Code Summary ======
# Unit tests for the discovery overlay layer: the route-key drift guard and the collection-scoped
# resolvers (collection schema → filters/weights/metadata + metagen targets, resolved vs unresolved).
# The pipeline-provider overlay was removed — providers are now carried by the recursive config_tree.

import pytest

from backend.routers.discovery.overlays import (
    OVERLAYS,
    build_dynamic_fields,
    validate_overlay_route_names,
)

_SCHEMA_FIELDS = [
    {"field_name": "dossier", "field_type": "string", "filterable": True, "semantic": True,
     "lexical": False, "enum_values": None, "required": False, "is_system": False},
    {"field_name": "statut", "field_type": "enum", "filterable": True, "semantic": False,
     "lexical": False, "enum_values": ["a", "b"], "required": False, "is_system": False},
    {"field_name": "filename", "field_type": "string", "filterable": True, "semantic": False,
     "lexical": True, "enum_values": None, "required": False, "is_system": True},
]


class TestOverlayDriftGuard:
    def test_passes_when_all_routes_known(self) -> None:
        validate_overlay_route_names(set(OVERLAYS.keys()) | {"other"})  # no raise

    def test_raises_on_unknown_route(self) -> None:
        with pytest.raises(ValueError):
            validate_overlay_route_names({"create_collection"})  # missing the rest


class TestCollectionOverlay:
    def test_unresolved_without_collection(self) -> None:
        fields = build_dynamic_fields("search_collection", None)
        by_path = {f.field_path: f for f in fields}
        assert set(by_path) == {"filters", "weights"}
        assert all(f.resolved is False and f.scope == "collection" for f in fields)

    def test_filters_resolved_from_schema(self) -> None:
        fields = build_dynamic_fields("search_collection", _SCHEMA_FIELDS)
        filters = next(f for f in fields if f.field_path == "filters")
        assert filters.resolved is True
        ids = {c.id for c in filters.choices}
        assert ids == {"dossier", "statut", "filename"}  # all filterable (incl. system)
        statut = next(c for c in filters.choices if c.id == "statut")
        # enum field exposes its operators + enum values
        op_field = next(p for p in statut.fields if p.name == "op")
        assert "in" in op_field.enum

    def test_weights_resolved_includes_content_and_named_vectors(self) -> None:
        fields = build_dynamic_fields("search_collection", _SCHEMA_FIELDS)
        weights = next(f for f in fields if f.field_path == "weights")
        ids = {c.id for c in weights.choices}
        assert "content_dense" in ids and "content_bm25" in ids
        assert "meta_dossier_dense" in ids  # dossier is semantic → named dense vector

    def test_ingest_metadata_only_custom_fields(self) -> None:
        fields = build_dynamic_fields("ingest_document", _SCHEMA_FIELDS)
        meta = fields[0]
        assert meta.field_path == "metadata"
        ids = {c.id for c in meta.choices}
        assert ids == {"dossier", "statut"}  # filename is system → excluded from writable metadata


# ─── Metagen-target overlay ─────────────────────────────────────────────────────

_SCHEMA_WITH_GENERATED = [
    # user field — should NOT appear as a metagen target
    {"field_name": "author", "field_type": "string", "filterable": False,
     "semantic": False, "lexical": False, "enum_values": None, "required": False,
     "is_system": False, "origin": "user"},
    # system field — should NOT appear
    {"field_name": "filename", "field_type": "string", "filterable": True,
     "semantic": False, "lexical": True, "enum_values": None, "required": False,
     "is_system": True, "origin": "system"},
    # generated fields — the ONLY valid metagen targets
    {"field_name": "kw", "field_type": "string[]", "filterable": False,
     "semantic": False, "lexical": False, "enum_values": None, "required": False,
     "is_system": False, "origin": "generated"},
    {"field_name": "summary", "field_type": "string", "filterable": False,
     "semantic": True, "lexical": False, "enum_values": None, "required": False,
     "is_system": False, "origin": "generated"},
]


class TestMetagenTargetOverlay:
    """The metagen.targets[].field overlay resolves only origin='generated' fields as choices."""

    def test_create_collection_includes_metagen_overlay(self) -> None:
        """create_collection always emits the metagen-target overlay (may be unresolved)."""
        fields = build_dynamic_fields("create_collection", None)
        paths = {f.field_path for f in fields}
        assert "pipeline.metagen.targets[].field" in paths

    def test_update_config_includes_metagen_overlay_with_patch_prefix(self) -> None:
        """update_config uses the 'patch.pipeline.' prefix for the metagen overlay."""
        fields = build_dynamic_fields("update_config", None)
        paths = {f.field_path for f in fields}
        assert "patch.pipeline.metagen.targets[].field" in paths

    def test_unresolved_when_schema_fields_none(self) -> None:
        """Without a collection context (schema_fields=None) the field comes back unresolved."""
        fields = build_dynamic_fields("create_collection", None)
        metagen_field = next(
            f for f in fields if f.field_path == "pipeline.metagen.targets[].field"
        )
        assert metagen_field.resolved is False
        assert metagen_field.capability == "metagen_target"
        assert metagen_field.scope == "collection"

    def test_resolved_from_generated_fields_only(self) -> None:
        """With schema_fields, the overlay resolves with only origin='generated' choices."""
        fields = build_dynamic_fields("create_collection", _SCHEMA_WITH_GENERATED)
        metagen_field = next(
            f for f in fields if f.field_path == "pipeline.metagen.targets[].field"
        )
        assert metagen_field.resolved is True
        choice_ids = {c.id for c in metagen_field.choices}
        assert choice_ids == {"kw", "summary"}
        # Non-generated fields must not appear
        assert "author" not in choice_ids
        assert "filename" not in choice_ids

    def test_resolved_empty_when_no_generated_fields(self) -> None:
        """A schema with no generated fields → resolved overlay with empty choices."""
        no_generated = [
            {"field_name": "author", "field_type": "string", "filterable": False,
             "semantic": False, "lexical": False, "enum_values": None, "required": False,
             "is_system": False, "origin": "user"},
        ]
        fields = build_dynamic_fields("create_collection", no_generated)
        metagen_field = next(
            f for f in fields if f.field_path == "pipeline.metagen.targets[].field"
        )
        assert metagen_field.resolved is True
        assert metagen_field.choices == []

    def test_choice_label_and_note_are_field_name_and_type(self) -> None:
        """Each Choice has id=field_name, label=field_name, note=field_type."""
        fields = build_dynamic_fields("create_collection", _SCHEMA_WITH_GENERATED)
        metagen_field = next(
            f for f in fields if f.field_path == "pipeline.metagen.targets[].field"
        )
        kw_choice = next(c for c in metagen_field.choices if c.id == "kw")
        assert kw_choice.label == "kw"
        assert kw_choice.note == "string[]"

    def test_metagen_overlay_kind_is_enum(self) -> None:
        """The metagen-target overlay uses kind='enum' (single-select from a fixed list)."""
        fields = build_dynamic_fields("create_collection", _SCHEMA_WITH_GENERATED)
        metagen_field = next(
            f for f in fields if f.field_path == "pipeline.metagen.targets[].field"
        )
        assert metagen_field.kind == "enum"
