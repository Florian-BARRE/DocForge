# ====== Code Summary ======
# The dynamic-overlay layer for /discovery: the ONLY hand-authored artifact — a tiny map binding a
# free-form/choice field of an endpoint (by route function name + field path) to a choice-source.
# Resolvers reuse what already exists: ProviderRegistry.describe_stages() for the pipeline, and the
# collection's metadata schema (+ the retrieval engine's vector plan) for search/ingest. The map is
# validated against the live routes at startup, so a renamed handler fails loudly, never silently.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from retrieval.field_index import CONTENT_DENSE, CONTENT_SPARSE, FieldIndexHelpers

# ====== Local Project Imports ======
from .models import Choice, DynamicField, ParamSchema

# (route_function_name, field_path) → choice-source tag. The whole hand-authored surface.
# Sources: "pipeline" (deployment, from describe_stages); "filters"/"weights"/"metadata" (collection).
OVERLAYS: dict[str, list[tuple[str, str]]] = {
    "create_collection": [("pipeline", "pipeline")],
    "update_config": [("patch.pipeline", "pipeline")],
    "search_collection": [("filters", "filters"), ("weights", "weights")],
    "search_within_document": [("filters", "filters"), ("weights", "weights")],
    "ingest_document": [("metadata", "metadata")],
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
    stages: list[dict[str, Any]],
    schema_fields: list[dict[str, Any]] | None,
) -> list[DynamicField]:
    """
    Build the dynamic-field overlays for one endpoint.

    Args:
        route_name (str): Route function name (the overlay key).
        stages (list[dict]): ``describe_stages()["stages"]`` (deployment choices).
        schema_fields (list[dict] | None): The collection's normalized metadata fields, or None when
            no collection_id was supplied (collection-scoped fields come back unresolved).

    Returns:
        list[DynamicField]: Overlays for this endpoint (empty for the common case).
    """
    out: list[DynamicField] = []
    for field_path, source in OVERLAYS.get(route_name, []):
        if source == "pipeline":
            out.extend(_pipeline_dynamic_fields(stages, prefix=f"{field_path}."))
        else:
            out.append(_collection_dynamic_field(source, schema_fields))
    return out


# ─── Pipeline (deployment-scoped) ──────────────────────────────────────────────

def _pipeline_dynamic_fields(stages: list[dict[str, Any]], prefix: str) -> list[DynamicField]:
    """One DynamicField per stage provider/method group, re-keyed onto the pipeline body path."""
    out: list[DynamicField] = []
    for stage in stages:
        for group in stage.get("groups", []):
            out.append(DynamicField(
                field_path=f"{prefix}{group['key']}",
                capability=group.get("capability", ""),
                kind=group.get("kind", "single"),
                scope="deployment",
                resolved=True,
                choices=[_provider_choice(p) for p in group.get("providers", [])],
            ))
    return out


def _provider_choice(provider: dict[str, Any]) -> Choice:
    """Map a describe_stages provider option to a discovery Choice (its params = conditional fields)."""
    return Choice(
        id=provider["id"],
        label=provider.get("label", ""),
        available=bool(provider.get("available", False)),
        selectable=bool(provider.get("selectable", False)),
        default=bool(provider.get("default", False)),
        note=provider.get("note", ""),
        fields=[ParamSchema.model_validate(p) for p in provider.get("params", [])],
    )


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
