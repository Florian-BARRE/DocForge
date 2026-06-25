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


class ProviderChoice(BaseModel):
    """
    One selectable provider/method option inside a ``chain``/``provider_union`` node.

    Mirrors :class:`Choice` but recursive: ``params`` is a list of :class:`ConfigNode`
    (not flat scalars), so a provider's own fields — INCLUDING a nested provider union
    such as the semantic split's ``embed`` — are fully expressible.

    Attributes:
        id (str): Provider/method discriminator (e.g. ``bge_server``, ``semantic``).
        label (str): Human-readable label shown in the picker.
        available (bool): Whether the provider's service is reachable in this deployment.
        selectable (bool): Whether the provider may be picked (some need per-collection config).
        default (bool): Whether this is the deployment-default choice for its category.
        note (str): Human hint (availability detail or caveat).
        params (list[ConfigNode]): The provider's own config fields, recursively described.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    label: str = ""
    available: bool = True
    selectable: bool = True
    default: bool = False
    note: str = ""
    params: list["ConfigNode"] = Field(default_factory=list)


class ConfigNode(BaseModel):
    """
    One recursive, schema-driven node of the full pipeline+search config tree.

    A single ``kind``-tagged node describes any field of ``PipelineConfig`` so a generic
    renderer can build the WHOLE configurator without hand-coded forms. Nesting is uniform
    and unbounded: an ``object`` recurses through ``children``; a ``chain``/``provider_union``
    recurses through each ``ProviderChoice.params``.

    Attributes:
        path (str): Full absolute dot-path (e.g. ``pipeline.embed.gate.min_score``) — the
            key the frontend's setPath/patch writes to.
        kind (str): ``scalar`` · ``enum`` · ``object`` · ``chain`` · ``provider_union``.
        label (str): Human-readable label.
        description (str): Tooltip / help text.
        default (Any): Default value (scalars/enums only; None for containers).
        resolved (bool): False when a ``collection_id`` is needed but absent (badge, not per-leaf).
        type (str | None): kind=scalar — ``bool`` · ``int`` · ``float`` · ``str`` · ``secret``.
        min / max (Any): kind=scalar — numeric bounds, when present.
        options (list[Any] | None): kind=enum — the allowed values.
        children (list[ConfigNode]): kind=object — nested nodes.
        multi (bool): kind=chain/provider_union — chain=True, single union=False.
        optional (bool): kind=provider_union — the union may be unset (a disabled choice).
        capability (str): kind=chain/provider_union — the registry category.
        choices (list[ProviderChoice]): kind=chain/provider_union — the available providers.
    """

    model_config = ConfigDict(extra="allow")

    path: str
    kind: str
    label: str = ""
    description: str = ""
    default: Any = None
    resolved: bool = True

    # kind=scalar
    type: str | None = None
    min: Any = None
    max: Any = None

    # kind=enum
    options: list[Any] | None = None

    # kind=object
    children: list["ConfigNode"] = Field(default_factory=list)

    # kind=chain / provider_union
    multi: bool = False
    optional: bool = False
    capability: str = ""
    choices: list[ProviderChoice] = Field(default_factory=list)


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
    config_tree: ConfigNode | None = None


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


# ProviderChoice.params references ConfigNode (defined after it) and ConfigNode.choices references
# ProviderChoice — resolve the mutual forward references now that both classes exist.
ProviderChoice.model_rebuild()
ConfigNode.model_rebuild()
