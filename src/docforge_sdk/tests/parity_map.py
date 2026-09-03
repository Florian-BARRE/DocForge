# ====== Code Summary ======
# Shared source of truth for the model↔OpenAPI parity checks: the mapping from each OpenAPI
# component-schema NAME to the SDK model that mirrors it, plus the deliberately-exempt models with
# their reasons. Imported by BOTH the offline parity test (diff vs a committed snapshot) and the live
# parity test (diff vs a running API's /openapi.json), so the two guards never drift apart. This is a
# helper module, not a test module — pytest does not collect it.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
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
    DocumentGridRow,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentSelector,
    DocumentSort,
    Pagination,
)
from docforge_sdk.models.documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted
from docforge_sdk.models.estimate import (
    CollectionEstimateRequest,
    CostEstimate,
    EstimateAssumptions,
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
from docforge_sdk.models.ir import DocumentIRModel, DocumentProvenance, IRAttempt, IRBlock, IREnrichment, IRFigure, IRTable
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
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchTarget,
)
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
    # Estimate
    "CollectionEstimateRequest": CollectionEstimateRequest,
    "EstimateAssumptions": EstimateAssumptions,
    "StageEstimate": StageEstimate,
    "VolumeEstimate": VolumeEstimate,
    "CostEstimate": CostEstimate,
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
}

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
}

__all__ = ["MODELS", "SKIPPED"]
