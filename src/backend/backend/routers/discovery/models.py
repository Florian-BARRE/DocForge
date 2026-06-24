# ====== Code Summary ======
# Response models for GET /api/v1/discovery — the unified, per-endpoint discovery surface a fully
# dynamic UI consumes. Contracts (input/output) are referenced verbatim from the app's generated
# OpenAPI (drift-proof); only the dynamic overlay (choices + conditional fields per free-form field)
# is added. ParamSchema describes one tunable parameter (type + bounds + optional enum) and is the
# shared primitive used by Choice.fields and the filter-operator descriptors in overlays.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class ParamSchema(BaseModel):
    """One tunable parameter — how a UI should render and bound an input (or a filter operator)."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Dot-path key for stage params, or local name inside a provider.")
    type: str = Field(..., description="Input type: bool · int · float · str · secret · rules.")
    label: str = ""
    default: Any = None
    description: str = ""
    min: Any = None
    max: Any = None
    enum: list[Any] | None = None


class OperationRef(BaseModel):
    """Stable identity of an endpoint: its HTTP method + OpenAPI path template."""

    method: str
    path: str


class FieldDescriptor(BaseModel):
    """One input field (path/query), projected verbatim from the OpenAPI parameter schema."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str | None = None
    required: bool = False
    default: Any = None
    min: Any = None
    max: Any = None
    enum: list[Any] | None = None
    description: str = ""


class ContractRef(BaseModel):
    """A reference to a request/response body schema living in the verbatim ``components`` block."""

    content_type: str
    schema_ref: str | None = Field(default=None, description="$ref into components, or None when inline/binary.")
    status: str | None = Field(default=None, description="HTTP status for an output contract.")


class Choice(BaseModel):
    """
    One selectable option for a dynamic field, with the conditional fields it unlocks.

    Mirrors the pipeline provider/method shape: pick ``id`` → render ``fields`` (its params).
    """

    model_config = ConfigDict(extra="allow")

    id: str
    label: str = ""
    available: bool = True
    selectable: bool = True
    default: bool = False
    note: str = ""
    fields: list[ParamSchema] = Field(default_factory=list)


class DynamicField(BaseModel):
    """
    A free-form/choice field of an endpoint that OpenAPI cannot describe, resolved at runtime.

    Attributes:
        field_path (str): Dot-path into the request body (e.g. ``pipeline.chunk.split_method``).
        capability (str): Logical capability (``chunk_strategy``, ``metadata_filter``, …).
        kind (str): ``single`` · ``multi`` · ``optional`` · ``map`` · ``weights``.
        scope (str): ``deployment`` (availability-driven) or ``collection`` (schema-driven).
        resolved (bool): False for a collection-scoped field requested without a ``collection_id``.
        choices (list[Choice]): The available options + their conditional fields.
        note (str): Human hint (e.g. why unresolved, or serialization caveats).
    """

    model_config = ConfigDict(extra="allow")

    field_path: str
    capability: str = ""
    kind: str = "single"
    scope: str = "deployment"
    resolved: bool = True
    choices: list[Choice] = Field(default_factory=list)
    note: str = ""


class EndpointDescriptor(BaseModel):
    """Everything a UI needs to render one endpoint: contract (from OpenAPI) + dynamic overlay."""

    model_config = ConfigDict(extra="allow")

    operation: OperationRef
    route_name: str
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    description: str = ""
    path_params: list[FieldDescriptor] = Field(default_factory=list)
    query_params: list[FieldDescriptor] = Field(default_factory=list)
    input: ContractRef | None = None
    output: ContractRef | None = None
    dynamic_fields: list[DynamicField] = Field(default_factory=list)


class DiscoveryResponse(BaseModel):
    """
    The full discovery payload: per-endpoint contracts + dynamic overlays + verbatim components.

    A UI builds itself entirely from this: it resolves ``input``/``output`` ``schema_ref`` against
    ``components`` (exactly as it would against ``/openapi.json``), renders scalar inputs from the
    schema, and renders each ``dynamic_fields`` entry as a choice picker whose selection reveals the
    chosen option's ``fields``. Nothing is hardcoded client-side.
    """

    openapi_version: str
    collection_id: str | None = None
    endpoints: list[EndpointDescriptor]
    components: dict[str, Any] = Field(..., description="Verbatim OpenAPI components (schemas).")
