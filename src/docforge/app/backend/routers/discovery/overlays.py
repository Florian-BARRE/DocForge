# ====== Code Summary ======
# The dynamic-overlay layer for /discovery: the ONLY hand-authored artifact — a tiny map binding a
# free-form/choice field of an endpoint (by route function name + field path) to a choice-source.
# Resolvers reuse what already exists: the collection's metadata schema (+ the retrieval engine's
# vector plan) for search/ingest/metagen choices. The full pipeline knob surface is now carried by the
# recursive config_tree (built from PipelineConfig by backend.libs.discovery.config_describer), which
# is strictly richer than the old flat per-stage overlay — so only collection-scoped overlays remain
# here. The map is validated against the live routes at startup, so a renamed handler fails loudly.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.search.field_index import CONTENT_DENSE, CONTENT_SPARSE, FieldIndexHelpers

# ====== Local Project Imports ======
from .models import Choice, DynamicField, ParamSchema

# (route_function_name, field_path) → choice-source tag. The whole hand-authored surface.
# Sources: "filters"/"weights"/"metadata" (collection); "metagen_targets" (collection — the
# generated-field options for pipeline.metagen.targets[*].field). The deployment-wide pipeline knobs
# are NOT overlaid here anymore — they live in the recursive config_tree. For "metagen_targets" the
# tuple's first element is the body PREFIX the source roots at ("pipeline" on create, "patch.pipeline"
# on update) so the emitted field paths line up with setPath.
OVERLAYS: dict[str, list[tuple[str, str]]] = {
    "create_collection": [("pipeline", "metagen_targets")],
    "update_config": [("patch.pipeline", "metagen_targets")],
    "search_collection": [("filters", "filters"), ("weights", "weights")],
    "search_within_document": [("filters", "filters"), ("weights", "weights")],
    "ingest_document": [("metadata", "metadata")],
}

# Routes that carry the FULL pipeline+search config in their request body — these get the recursive
# `config_tree` (describe(PipelineConfig)) in addition to the flat `dynamic_fields`. Each maps to the
# absolute dot-path prefix the tree is rooted at, so the frontend's setPath/patch targets line up.
CONFIG_BEARING_ROUTES: dict[str, str] = {
    "create_collection": "pipeline",
    "update_config": "patch.pipeline",
}

# Per collection-scoped source: its capability + UI kind (used for both resolved + unresolved cases).
_COLLECTION_SOURCES: dict[str, dict[str, str]] = {
    "filters": {"capability": "metadata_filter", "kind": "map"},
    "weights": {"capability": "fusion_weight", "kind": "weights"},
    "metadata": {"capability": "metadata_write", "kind": "map"},
}

# Filter operators offered per metadata field type (matches the Qdrant filter grammar search honors).
_FILTER_OPS: dict[str, list[str]] = {
    "number": ["eq", "gte", "lte", "gt", "lt"],
    "date": ["eq", "gte", "lte", "gt", "lt"],
    "enum": ["in", "eq"],
    "bool": ["eq"],
    "string": ["match", "eq"],
    "string[]": ["any", "eq"],
}
# Metadata field type → the UI input type for its value.
_VALUE_TYPE: dict[str, str] = {
    "number": "float", "date": "str", "bool": "bool", "enum": "str", "string": "str", "string[]": "str",
}


def validate_overlay_route_names(route_names: set[str]) -> None:
    """
    Fail fast if an overlay key does not match a live route function name.

    Args:
        route_names (set[str]): The app's route function names.

    Raises:
        ValueError: When an OVERLAYS key has no corresponding route (drift guard).
    """
    missing = sorted(set(OVERLAYS) - route_names)
    if missing:
        raise ValueError(f"discovery overlay references unknown route(s): {missing}")


def build_dynamic_fields(
    route_name: str,
    schema_fields: list[dict[str, Any]] | None,
) -> list[DynamicField]:
    """
    Build the dynamic-field overlays for one endpoint.

    Args:
        route_name (str): Route function name (the overlay key).
        schema_fields (list[dict] | None): The collection's normalized metadata fields, or None when
            no collection_id was supplied (collection-scoped fields come back unresolved).

    Returns:
        list[DynamicField]: Overlays for this endpoint (empty for the common case).
    """
    out: list[DynamicField] = []
    for field_path, source in OVERLAYS.get(route_name, []):
        if source == "metagen_targets":
            # field_path is the body prefix ("pipeline" / "patch.pipeline") the target list roots at.
            out.append(_metagen_target_field(prefix=f"{field_path}.", schema_fields=schema_fields))
        else:
            out.append(_collection_dynamic_field(source, schema_fields))
    return out


# ─── Collection-scoped (filters / weights / metadata) ──────────────────────────

def _collection_dynamic_field(source: str, schema_fields: list[dict[str, Any]] | None) -> DynamicField:
    """Build a collection-scoped DynamicField, or an unresolved stub when no collection is given."""
    meta = _COLLECTION_SOURCES[source]
    # 1. Unresolved: caller did not supply a collection_id
    if schema_fields is None:
        return DynamicField(
            field_path=source, capability=meta["capability"], kind=meta["kind"],
            scope="collection", resolved=False,
            note="Re-request with ?collection_id=<uuid> to resolve choices from the collection schema.",
        )
    # 2. Resolved per source
    if source == "weights":
        return _weights_field(schema_fields)
    if source == "filters":
        choices = [_filter_choice(f) for f in schema_fields if f.get("filterable")]
        note = "Pick a field, then its operator + value; combine into the Qdrant filter."
    else:  # metadata (ingest) — writable custom fields only
        choices = [_metadata_choice(f) for f in schema_fields if not f.get("is_system")]
        note = "Build the object, then send it as a JSON string in the multipart 'metadata' field."
    return DynamicField(
        field_path=source, capability=meta["capability"], kind=meta["kind"],
        scope="collection", resolved=True, choices=choices, note=note,
    )


def _filter_choice(field: dict[str, Any]) -> Choice:
    """A filterable field → a Choice whose fields are {operator (enum), value (typed)}."""
    ftype = field.get("field_type", "string")
    ops = _FILTER_OPS.get(ftype, ["eq"])
    value: dict[str, Any] = {"name": "value", "type": _VALUE_TYPE.get(ftype, "str"), "label": "value"}
    if ftype == "enum" and field.get("enum_values"):
        value["enum"] = field["enum_values"]
    return Choice(
        id=field["field_name"], label=field["field_name"], note=f"{ftype} filter",
        fields=[
            ParamSchema.model_validate({"name": "op", "type": "str", "label": "operator", "enum": ops, "default": ops[0]}),
            ParamSchema.model_validate(value),
        ],
    )


def _metadata_choice(field: dict[str, Any]) -> Choice:
    """A writable custom field → a Choice with a single typed value field."""
    ftype = field.get("field_type", "string")
    value: dict[str, Any] = {"name": "value", "type": _VALUE_TYPE.get(ftype, "str"), "label": "value"}
    if ftype == "enum" and field.get("enum_values"):
        value["enum"] = field["enum_values"]
    return Choice(
        id=field["field_name"], label=field["field_name"],
        note="required" if field.get("required") else "optional",
        fields=[ParamSchema.model_validate(value)],
    )


def _metagen_target_field(
    prefix: str, schema_fields: list[dict[str, Any]] | None
) -> DynamicField:
    """
    Overlay the ``metagen.targets[].field`` picker with the collection's generated field names.

    The describer renders ``pipeline.metagen.targets`` as a generic ``object_list`` whose ``field``
    child is a free string; this overlay injects the actual choosable options — the metadata fields
    authored with ``origin="generated"`` — so the UI offers a dropdown bound to the same path the
    object_list item renders (``{prefix}metagen.targets[].field``). The describer stays generic;
    only the option set is collection data.

    Args:
        prefix (str): The body prefix the target list roots at ("pipeline." / "patch.pipeline.").
        schema_fields (list[dict] | None): The collection's normalized metadata fields, or None when
            no collection_id was supplied (the field comes back unresolved).

    Returns:
        DynamicField: The (resolved or unresolved) target-field option overlay.
    """
    field_path = f"{prefix}metagen.targets[].field"
    # 1. Unresolved: no collection_id → cannot list its generated fields yet.
    if schema_fields is None:
        return DynamicField(
            field_path=field_path, capability="metagen_target", kind="enum",
            scope="collection", resolved=False,
            note="Re-request with ?collection_id=<uuid> to resolve the generated-field options.",
        )
    # 2. Resolved: one Choice per origin="generated" field (the only valid metagen targets).
    choices = [
        Choice(id=f["field_name"], label=f["field_name"], note=f.get("field_type", "string"))
        for f in schema_fields
        if f.get("origin") == "generated"
    ]
    return DynamicField(
        field_path=field_path, capability="metagen_target", kind="enum",
        scope="collection", resolved=True, choices=choices,
        note="Pick a generated metadata field (origin='generated') for this metagen target.",
    )


def _weights_field(schema_fields: list[dict[str, Any]]) -> DynamicField:
    """Named-vector fusion weights — derived from the same vector plan the retrieval engine fuses."""
    plan = FieldIndexHelpers.derive_vector_plan(schema_fields)

    def _vec_choice(vector: str, label: str) -> Choice:
        return Choice(
            id=vector, label=label,
            fields=[ParamSchema.model_validate(
                {"name": "weight", "type": "float", "label": "weight", "default": 1.0, "min": 0.0, "max": 10.0}
            )],
        )

    choices = [_vec_choice(CONTENT_DENSE, "content (dense)"), _vec_choice(CONTENT_SPARSE, "content (BM25)")]
    choices += [_vec_choice(fv.vector, f"{fv.name} (dense)") for fv in plan.dense]
    choices += [_vec_choice(fv.vector, f"{fv.name} (BM25)") for fv in plan.sparse]
    return DynamicField(
        field_path="weights", capability="fusion_weight", kind="weights",
        scope="collection", resolved=True, choices=choices,
        note="Per named-vector RRF weight override (vector_name → weight).",
    )
