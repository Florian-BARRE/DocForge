# ====== Code Summary ======
# Unit tests for the discovery overlay layer: the route-key drift guard and the pure resolvers
# (pipeline stages → DynamicFields; collection schema → filters/weights, resolved vs unresolved).

import pytest

from backend.routers.discovery.overlays import (
    OVERLAYS,
    build_dynamic_fields,
    validate_overlay_route_names,
)

# A minimal describe_stages-style stub: one stage with a single-select chunk_strategy group.
_STAGES = [
    {
        "id": "s4", "groups": [
            {
                "key": "chunk.split_method", "kind": "single", "capability": "chunk_strategy",
                "providers": [
                    {"id": "token_budget", "label": "Token budget", "available": True, "selectable": True,
                     "default": True, "note": "", "params": [
                         {"name": "max_tokens", "type": "int", "default": 512, "min": 64, "max": 4096}]},
                    {"id": "semantic", "label": "Semantic", "available": False, "selectable": True, "params": []},
                ],
            },
        ],
    },
]

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


class TestPipelineOverlay:
    def test_create_collection_pipeline_fields(self) -> None:
        fields = build_dynamic_fields("create_collection", _STAGES, None)
        assert len(fields) == 1
        f = fields[0]
        assert f.field_path == "pipeline.chunk.split_method"
        assert f.kind == "single" and f.capability == "chunk_strategy" and f.scope == "deployment"
        ids = [c.id for c in f.choices]
        assert ids == ["token_budget", "semantic"]
        # Conditional fields come from the provider params (model-derived)
        tb = next(c for c in f.choices if c.id == "token_budget")
        assert tb.fields[0].name == "max_tokens" and tb.fields[0].min == 64

    def test_update_config_prefix(self) -> None:
        fields = build_dynamic_fields("update_config", _STAGES, None)
        assert fields[0].field_path == "patch.pipeline.chunk.split_method"


class TestCollectionOverlay:
    def test_unresolved_without_collection(self) -> None:
        fields = build_dynamic_fields("search_collection", _STAGES, None)
        by_path = {f.field_path: f for f in fields}
        assert set(by_path) == {"filters", "weights"}
        assert all(f.resolved is False and f.scope == "collection" for f in fields)

    def test_filters_resolved_from_schema(self) -> None:
        fields = build_dynamic_fields("search_collection", _STAGES, _SCHEMA_FIELDS)
        filters = next(f for f in fields if f.field_path == "filters")
        assert filters.resolved is True
        ids = {c.id for c in filters.choices}
        assert ids == {"dossier", "statut", "filename"}  # all filterable (incl. system)
        statut = next(c for c in filters.choices if c.id == "statut")
        # enum field exposes its operators + enum values
        op_field = next(p for p in statut.fields if p.name == "op")
        assert "in" in op_field.enum

    def test_weights_resolved_includes_content_and_named_vectors(self) -> None:
        fields = build_dynamic_fields("search_collection", _STAGES, _SCHEMA_FIELDS)
        weights = next(f for f in fields if f.field_path == "weights")
        ids = {c.id for c in weights.choices}
        assert "content_dense" in ids and "content_bm25" in ids
        assert "meta_dossier_dense" in ids  # dossier is semantic → named dense vector

    def test_ingest_metadata_only_custom_fields(self) -> None:
        fields = build_dynamic_fields("ingest_document", _STAGES, _SCHEMA_FIELDS)
        meta = fields[0]
        assert meta.field_path == "metadata"
        ids = {c.id for c in meta.choices}
        assert ids == {"dossier", "statut"}  # filename is system → excluded from writable metadata
