# ====== Code Summary ======
# GET /api/v1/discovery — the unified, per-endpoint discovery surface. Input/output contracts are
# taken verbatim from the app's generated OpenAPI (drift-proof); the dynamic overlay (choices +
# conditional fields for free-form fields) is layered on via the tiny OVERLAYS map. An optional
# ?collection_id resolves collection-scoped choices (search filters/weights, ingest metadata) from
# that collection's metadata schema. A UI builds itself entirely from this one call.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute

# ====== Internal Project Imports ======
from common_libs.domain.metadata import schema_field_dicts

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.utils.error_handling import auto_handle_errors
from .models import (
    ContractRef,
    DiscoveryResponse,
    EndpointDescriptor,
    FieldDescriptor,
    OperationRef,
)
from .overlays import build_dynamic_fields

router = APIRouter(tags=["discovery"])

# Output contract: the first 2xx response we find (create=201, ingest/reingest=202, rest=200).
_SUCCESS_CODES: tuple[str, ...] = ("200", "201", "202", "204")


@router.get("", response_model=DiscoveryResponse)
@auto_handle_errors
async def get_discovery(request: Request, collection_id: uuid.UUID | None = None) -> DiscoveryResponse:
    """
    Describe every endpoint: input/output contract + dynamic choices/conditional fields.

    Args:
        request (Request): Used to read the app's generated OpenAPI (contracts) and routes.
        collection_id (uuid.UUID | None): When given, resolves collection-scoped choices (search
            filters/weights, ingest metadata) from that collection's metadata schema.

    Returns:
        DiscoveryResponse: Per-endpoint descriptors + verbatim OpenAPI components.
    """
    # 1. Contracts come straight from FastAPI's generated OpenAPI — never hand-assembled
    openapi = request.app.openapi()
    paths = openapi.get("paths", {})

    # 2. Choice sources: deployment pipeline (always) + the collection schema (only when scoped)
    stages = CONTEXT.registry.describe_stages()["stages"]
    schema_fields = await _load_schema_fields(collection_id) if collection_id is not None else None

    # 3. One descriptor per (route, method), enriched with its dynamic-field overlays
    endpoints: list[EndpointDescriptor] = []
    for route in request.app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        route_name = route.endpoint.__name__
        path_item = paths.get(route.path, {})
        for method in sorted(m for m in route.methods if m not in {"HEAD", "OPTIONS"}):
            op = path_item.get(method.lower())
            if op is None:
                continue
            endpoints.append(_build_endpoint(route_name, method, route.path, route.tags, op, stages, schema_fields))

    return DiscoveryResponse(
        openapi_version=openapi.get("openapi", ""),
        collection_id=str(collection_id) if collection_id is not None else None,
        endpoints=endpoints,
        components=openapi.get("components", {}),
    )


# ─── Internal ──────────────────────────────────────────────────────────────────

async def _load_schema_fields(collection_id: uuid.UUID) -> list[dict[str, Any]]:
    """Load the collection's normalized metadata schema (404 if missing) — shared with search."""
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return schema_field_dicts(collection.metadata_fields)


def _build_endpoint(
    route_name: str,
    method: str,
    path: str,
    tags: list[str],
    op: dict[str, Any],
    stages: list[dict[str, Any]],
    schema_fields: list[dict[str, Any]] | None,
) -> EndpointDescriptor:
    """Assemble one endpoint descriptor from its OpenAPI operation + dynamic overlays."""
    params = op.get("parameters", [])
    return EndpointDescriptor(
        operation=OperationRef(method=method, path=path),
        route_name=route_name,
        tags=list(tags or op.get("tags", [])),
        summary=op.get("summary", ""),
        description=op.get("description", ""),
        path_params=[_field_descriptor(p) for p in params if p.get("in") == "path"],
        query_params=[_field_descriptor(p) for p in params if p.get("in") == "query"],
        input=_input_contract(op),
        output=_output_contract(op),
        dynamic_fields=build_dynamic_fields(route_name, stages, schema_fields),
    )


def _field_descriptor(param: dict[str, Any]) -> FieldDescriptor:
    """Project an OpenAPI parameter into a FieldDescriptor (type/bounds/default from its schema)."""
    schema = param.get("schema", {})
    return FieldDescriptor(
        name=param.get("name", ""),
        type=schema.get("type"),
        required=bool(param.get("required", False)),
        default=schema.get("default"),
        min=schema.get("minimum"),
        max=schema.get("maximum"),
        enum=schema.get("enum"),
        description=param.get("description", ""),
    )


def _input_contract(op: dict[str, Any]) -> ContractRef | None:
    """Reference the request body schema (first content type), or None when there is no body."""
    content = op.get("requestBody", {}).get("content", {})
    if not content:
        return None
    content_type = next(iter(content))
    return ContractRef(content_type=content_type, schema_ref=_schema_ref(content[content_type].get("schema", {})))


def _output_contract(op: dict[str, Any]) -> ContractRef | None:
    """Reference the first 2xx response body schema (handles 200/201/202; None for binary/empty)."""
    responses = op.get("responses", {})
    for code in _SUCCESS_CODES:
        if code in responses:
            content = responses[code].get("content", {})
            if not content:
                return ContractRef(content_type="", schema_ref=None, status=code)
            content_type = "application/json" if "application/json" in content else next(iter(content))
            return ContractRef(
                content_type=content_type,
                schema_ref=_schema_ref(content[content_type].get("schema", {})),
                status=code,
            )
    return None


def _schema_ref(schema: dict[str, Any]) -> str | None:
    """Extract a ``$ref`` from a schema node (direct or wrapped in allOf), else None for inline."""
    if "$ref" in schema:
        return schema["$ref"]
    for wrapper in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(wrapper, []):
            if isinstance(sub, dict) and "$ref" in sub:
                return sub["$ref"]
    return None
