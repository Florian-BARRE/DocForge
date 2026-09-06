# ====== Code Summary ======
# Shared source of truth for the model↔OpenAPI parity checks: the mapping from each OpenAPI
# component-schema NAME to the SDK model that mirrors it, plus the deliberately-exempt models with
# their reasons. Imported by BOTH the offline parity test (diff vs a committed snapshot) and the live
# parity test (diff vs a running API's /openapi.json), so the two guards never drift apart. This is a
# helper module, not a test module — pytest does not collect it.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
from docforge_sdk.models._shared import KeyPermissions
from docforge_sdk.models.audit import AuditEntry, AuditPage
from docforge_sdk.models.auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest, WhoAmI
from docforge_sdk.models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionContractSchemaResponse,
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    FieldSpec,
    ReingestJobHandle,
    UpdateCollectionRequest,
)
from docforge_sdk.models.corpus import (
    BulkDeleteResponse,
    BulkEnabledResponse,
    BulkReingestResponse,
    DateRange,
    DocumentFilter,
    DocumentGridRow,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentSelector,
    DocumentSort,
    MetadataFilter,
    NumberRange,
    Pagination,
    TextFilter,
)
from docforge_sdk.models.documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted
from docforge_sdk.models.estimate import (
    AssumptionOverrides,
    CollectionEstimateRequest,
    CostEstimate,
    EstimateAssumptions,
    EstimateOverrides,
    ModelRateOverride,
    RateOverrides,
    StageEstimate,
    VolumeEstimate,
)
from docforge_sdk.models.explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    DocumentDetail,
    DocumentListItem,
    MetadataValue,
    PageInfo,
)
from docforge_sdk.models.health import (
    CollectionHealthResponse,
    CollectionHealthSummary,
    IngestHealth,
    ProviderProbeResult,
    SearchHealth,
    SearchIndex,
)
from docforge_sdk.models.ir import (
    DocumentIRModel,
    DocumentProvenance,
    IRAttempt,
    IRBlock,
    IREnrichment,
    IRFigure,
    IRTable,
)
from docforge_sdk.models.jobs import (
    CancelResult,
    JobEvent,
    JobPage,
    JobStatus,
    JobTrace,
    QueueDepth,
    StageDurations,
    WorkerActivity,
    WorkersLive,
)
from docforge_sdk.models.jobs import (
    CollectionCost as _CollectionCost,
)
from docforge_sdk.models.pipelines import (
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelineSurface,
    StageApplyResponse,
    StageViewResponse,
)
from docforge_sdk.models.search import (
    BlockLocation,
    SearchCost,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchTarget,
)
from docforge_sdk.models.snippets import CollectionSnippet, SnippetImportResult
from docforge_sdk.models.storage import (
    CollectionStorageResponse,
    DocumentStorageModel,
    PostgresFootprintModel,
    QdrantFootprintModel,
    S3FootprintModel,
)
from docforge_sdk.models.transfers import TransferAccepted, TransferStatus

# Maps the OpenAPI component-schema NAME to the SDK model that mirrors it. A handful of SDK classes
# drop the backend's "Model" suffix (FieldSpec, SearchTarget, SearchHit), so the key is authoritative.
MODELS: dict[str, type[BaseModel]] = {
    # Audit
    "AuditEntry": AuditEntry,
    "AuditPage": AuditPage,
    # Corpus grid + bulk ops
    "DocumentSort": DocumentSort,
    "Pagination": Pagination,
    "DocumentQueryRequest": DocumentQueryRequest,
    "DocumentGridRow": DocumentGridRow,
    "DocumentQueryResponse": DocumentQueryResponse,
    "DocumentSelector": DocumentSelector,
    "BulkDeleteResponse": BulkDeleteResponse,
    "BulkEnabledResponse": BulkEnabledResponse,
    "BulkReingestResponse": BulkReingestResponse,
    # Jobs telemetry
    "QueueDepth": QueueDepth,
    "StageDurations": StageDurations,
    "CollectionCost": _CollectionCost,
    # Discovery + introspection
    "CollectionContractSchemaResponse": CollectionContractSchemaResponse,
    "WhoAmI": WhoAmI,
    # Auth
    "CreateKeyRequest": CreateKeyRequest,
    "RotateKeyRequest": RotateKeyRequest,
    "CreatedKey": CreatedKey,
    "KeyInfo": KeyInfo,
    # Auth — the scoped per-key permission block (nested on Create/RotateKeyRequest). Its enum leaf
    # (Capability) is SKIPPED as a pure StrEnum.
    "KeyPermissions": KeyPermissions,
    # Health (collection health probe + list-attached summary; bare-root liveness is SKIPPED).
    # Pure StrEnum schemas (ProbeStatus/HealthVerdict/CollectionListVerdict) are NOT tracked here —
    # they have no model_json_schema() of their own (see SKIPPED); their values are still exercised
    # indirectly via the composite models below that carry them as fields.
    "ProviderProbeResult": ProviderProbeResult,
    "IngestHealth": IngestHealth,
    "SearchIndex": SearchIndex,
    "SearchHealth": SearchHealth,
    "CollectionHealthResponse": CollectionHealthResponse,
    "CollectionHealthSummary": CollectionHealthSummary,
    # Collections
    "FieldSpecModel": FieldSpec,
    "CollectionModel": CollectionModel,
    "CollectionListItem": CollectionListItem,
    "CreateCollectionRequest": CreateCollectionRequest,
    "UpdateCollectionRequest": UpdateCollectionRequest,
    "BulkReingestRequest": BulkReingestRequest,
    "ReingestJobHandle": ReingestJobHandle,
    "BulkReingestAccepted": BulkReingestAccepted,
    # Documents
    "UploadAccepted": UploadAccepted,
    "EnabledPatch": EnabledPatch,
    "DocumentEnabledResponse": DocumentEnabledResponse,
    # Corpus grid filters (also reused by CollectionEstimateRequest.filter below).
    "TextFilter": TextFilter,
    "NumberRange": NumberRange,
    "DateRange": DateRange,
    "MetadataFilter": MetadataFilter,
    "DocumentFilter": DocumentFilter,
    # Estimate
    "CollectionEstimateRequest": CollectionEstimateRequest,
    "EstimateAssumptions": EstimateAssumptions,
    "StageEstimate": StageEstimate,
    "VolumeEstimate": VolumeEstimate,
    "CostEstimate": CostEstimate,
    # Estimate overrides — round-trip on CollectionModel/UpdateCollectionRequest.estimate_overrides.
    "ModelRateOverride": ModelRateOverride,
    "RateOverrides": RateOverrides,
    "AssumptionOverrides": AssumptionOverrides,
    "EstimateOverrides": EstimateOverrides,
    # Explorer
    "MetadataValue": MetadataValue,
    "DocumentListItem": DocumentListItem,
    "DocumentDetail": DocumentDetail,
    "PageInfo": PageInfo,
    "ChunkInfo": ChunkInfo,
    "ChunkEnabledPatch": ChunkEnabledPatch,
    "BulkChunkEnabledPatch": BulkChunkEnabledPatch,
    "ChunkEnabledResult": ChunkEnabledResult,
    "BulkChunkEnabledResponse": BulkChunkEnabledResponse,
    # IR
    "IRBlock": IRBlock,
    "IRTable": IRTable,
    "IRFigure": IRFigure,
    "IRAttempt": IRAttempt,
    "IREnrichment": IREnrichment,
    "DocumentIRModel": DocumentIRModel,
    "DocumentProvenance": DocumentProvenance,
    # Search
    "SearchTargetModel": SearchTarget,
    "SearchRequest": SearchRequest,
    "BlockLocationModel": BlockLocation,
    "SearchHitModel": SearchHit,
    "SearchCostModel": SearchCost,
    "SearchResponse": SearchResponse,
    # Jobs
    "JobStatus": JobStatus,
    "JobPage": JobPage,
    "JobEvent": JobEvent,
    "JobTrace": JobTrace,
    "WorkerActivity": WorkerActivity,
    "WorkersLive": WorkersLive,
    "CancelResult": CancelResult,
    # Pipelines (opaque graph JSON typed as dicts, but property names + required still 1:1)
    "PipelineSurface": PipelineSurface,
    "PipelineIndexResponse": PipelineIndexResponse,
    "PipelineDesignResponse": PipelineDesignResponse,
    "InspectResponse": InspectResponse,
    "EditResponse": EditResponse,
    "StageViewResponse": StageViewResponse,
    "StageApplyResponse": StageApplyResponse,
    # Storage
    "S3FootprintModel": S3FootprintModel,
    "PostgresFootprintModel": PostgresFootprintModel,
    "QdrantFootprintModel": QdrantFootprintModel,
    "DocumentStorageModel": DocumentStorageModel,
    "CollectionStorageResponse": CollectionStorageResponse,
    # Transfers
    "TransferAccepted": TransferAccepted,
    "TransferStatus": TransferStatus,
    # Collection config snippets (granular pipeline/search/schema export-import).
    "CollectionSnippet": CollectionSnippet,
    "SnippetImportResult": SnippetImportResult,
}

# Every schema nested inside the pipeline engine's OPAQUE graph JSON (the blob / palette / issues /
# explored / stages payloads). Per docforge_sdk/models/pipelines.py's module docstring, this is a
# DELIBERATE design choice, not a coverage gap: "The graph JSON is OPAQUE to the SDK: every payload the
# engine owns ... is typed as dict/list[dict]; only the stable ENVELOPE fields carry precise types."
# The matching request-body schemas (InspectRequest/EditRequest/StageViewRequest/StageApplyRequest) are
# built and sent as raw dicts too (see resources/pipelines.py: `json={"blob": blob}` etc.), so they are
# exempt for the identical reason — there is no pydantic request model to mirror them against.
_OPAQUE_PIPELINE_BLOB_REASON = (
    "opaque pipeline-graph JSON (by design, not an oversight) — the SDK deliberately keeps the "
    "engine-owned blob/palette/issues/explored/stages payload untyped (dict/list[dict]); only the "
    "response ENVELOPE is mirrored. See the module docstring of docforge_sdk/models/pipelines.py and "
    "the request-spec builders in docforge_sdk/resources/pipelines.py."
)

# Transitions, bindings, node blobs, edit operations, palette/introspection and stage view/apply —
# every nested member of the opaque pipeline blob (see _OPAQUE_PIPELINE_BLOB_REASON above).
_PIPELINE_BLOB_SCHEMAS: list[str] = [
    # Transitions (control edges).
    "Transition",
    "Always",
    "OnSuccess",
    "OnFailure",
    "ScoreBelow",
    "WhenEquals",
    "Condition",
    # Bindings (data edges).
    "Binding",
    "FromRunInput",
    "FromNode",
    "FromGroupInput",
    "FromFirst",
    # Node blob variants (the graph's own node JSON).
    "NodeBlob-Input",
    "NodeBlob-Output",
    "GroupNodeBlob-Input",
    "GroupNodeBlob-Output",
    "ForEachNodeBlob-Input",
    "ForEachNodeBlob-Output",
    "ActionNodeBlob",
    # Edit operations (server-side graph mutation) + their request envelope.
    "AddNode",
    "AddLoop",
    "RemoveNode",
    "SetAfter",
    "SetBinding",
    "SetChain",
    "SetCondition",
    "SetConfig",
    "SetLoopProp",
    "SetProvider",
    "SetStack",
    "SetStageConfig",
    "InsertFragment",
    "DisableStage",
    "EnableStage",
    "EditOperation",
    "EditRequest",
    "InspectRequest",
    # Palette / introspection (describes the graph and its available blocks).
    "ExploredNode",
    "NodeDescription",
    "NodeType",
    "IoSlot",
    "FamilyCatalog",
    "FamilyMode",
    "Palette",
    "ErrorPolicy",
    "MechanicCard",
    "MechanicsDescription",
    "ArtefactCard",
    "ChainSpec",
    "ChainStep",
    "ChainView",
    "StackMethod",
    # Stage view / apply (the stackable-stage editing surface).
    "StageAction",
    "StageApplyRequest",
    "StageKind",
    "StageView",
    "StageViewRequest",
    # Validation issues surfaced inside the opaque `issues: list[dict]` field.
    "ValidationCode",
    "ValidationIssue",
]

# SDK models deliberately WITHOUT a 1:1 OpenAPI schema, each with the reason it is skipped.
SKIPPED: dict[str, str] = {
    "HealthStatus": "health route is registered with include_in_schema=False (absent from the schema).",
    "BlobContent": "SDK-only wrapper — the blobs endpoint streams raw bytes, not a JSON schema.",
    "ProbeStatus": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values "
    "are exercised indirectly via ProviderProbeResult.status.",
    "HealthVerdict": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values "
    "are exercised indirectly via CollectionHealthResponse.verdict.",
    "CollectionListVerdict": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its "
    "values are exercised indirectly via CollectionHealthSummary.verdict.",
    # Pure StrEnum leaves of now-tracked composite models — same gotcha as the health enums above.
    "Capability": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values are "
    "exercised indirectly via KeyPermissions.capabilities.",
    "FieldType": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values are "
    "exercised indirectly via FieldSpecModel.field_type.",
    "FieldOrigin": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values are "
    "exercised indirectly via FieldSpecModel.origin.",
    "FieldScope": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values are "
    "exercised indirectly via FieldSpecModel.scope.",
    "SourceKind": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values are "
    "exercised indirectly via DocumentDetail.source_kind.",
    "DocumentStatus": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values "
    "are exercised indirectly via DocumentFilter.status / DocumentListItem.status.",
    "EnrichmentKind": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values "
    "are exercised indirectly via IREnrichment.kind.",
    "EnrichmentStatus": "pure StrEnum, not a BaseModel — no model_json_schema() of its own; its values "
    "are exercised indirectly via IREnrichment.status.",
    # FastAPI/framework-generated schemas — no hand-written SDK model exists or should exist for these.
    "HTTPValidationError": "FastAPI-generated 422 envelope — the SDK maps non-2xx responses to typed "
    "exceptions (see docforge_sdk/_exceptions.py) instead of parsing this body.",
    "ValidationError": "FastAPI-generated per-field validation error, nested only inside "
    "HTTPValidationError.detail — see that entry.",
    "Body_upload_document_api_v1_documents_post": "FastAPI-generated multipart form schema — the SDK "
    "sends this upload as raw httpx files/data parts (resources/documents.py), not a JSON body model.",
    "Body_import_collection_api_v1_collections_import_post": "FastAPI-generated multipart form schema "
    "— the SDK streams this import as raw httpx files/data parts (resources/transfers.py), not a JSON "
    "body model.",
    # Opaque pipeline-graph JSON (59 schemas) — see _OPAQUE_PIPELINE_BLOB_REASON above.
    **{name: _OPAQUE_PIPELINE_BLOB_REASON for name in _PIPELINE_BLOB_SCHEMAS},
}

__all__ = ["MODELS", "SKIPPED"]
