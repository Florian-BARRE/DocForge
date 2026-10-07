# ------------------- Shared vocabulary ------------------- #
from ._shared import (
    Capability,
    DocumentStatus,
    EnrichmentKind,
    EnrichmentStatus,
    FieldOrigin,
    FieldScope,
    FieldType,
    KeyPermissions,
    SourceKind,
)

# ------------------- Audit models ------------------- #
from .audit import AuditEntry, AuditPage

# ------------------- Auth models ------------------- #
from .auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest, WhoAmI

# ------------------- Blobs models ------------------- #
from .blobs import BlobContent

# ------------------- Capabilities models ------------------- #
from .capabilities import CapabilitiesResponse, CapabilityMatrix, ServiceInfo

# ------------------- Collections models ------------------- #
from .collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionContractSchemaResponse,
    CollectionDescription,
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    FieldGuide,
    FieldSpec,
    ReingestJobHandle,
    SearchTargetGuide,
    UpdateCollectionRequest,
    UpdateCollectionResponse,
)

# ------------------- Corpus filter + grid models ------------------- #
from .corpus import (
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

# ------------------- Documents models ------------------- #
from .documents import (
    DocumentEnabledResponse,
    DocumentView,
    EnabledPatch,
    MetadataUpdateResponse,
    MetadataValuesPatch,
    UploadAccepted,
)

# ------------------- Estimate models ------------------- #
from .estimate import (
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

# ------------------- Explorer models ------------------- #
from .explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkContext,
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    ChunkPage,
    ContextChunk,
    DocumentDetail,
    DocumentListItem,
    DocumentOutline,
    MetadataValue,
    OutlineHeading,
    PageInfo,
)

# ------------------- Health models ------------------- #
from .health import (
    CollectionHealthResponse,
    CollectionHealthSummary,
    CollectionListVerdict,
    HealthStatus,
    HealthVerdict,
    IngestHealth,
    ProbeStatus,
    ProviderProbeResult,
    SearchHealth,
    SearchIndex,
)

# ------------------- Index rebuild models ------------------- #
from .index_rebuild import RebuildIndexAccepted

# ------------------- IR models ------------------- #
from .ir import (
    DocumentIRModel,
    DocumentProvenance,
    IRBlock,
    IREnrichment,
    IRFigure,
    IRTable,
)

# ------------------- Jobs models ------------------- #
from .jobs import (
    CancelResult,
    CollectionCost,
    CollectionFailureBucket,
    FailureBreakdown,
    FailureBucket,
    JobEvent,
    JobEventPayload,
    JobPage,
    JobStatus,
    JobTimeseries,
    JobTrace,
    NewFailures,
    QueueDepth,
    StageDurations,
    TimeseriesBucket,
    WorkerActivity,
    WorkersLive,
)

# ------------------- Pipelines models ------------------- #
from .pipelines import (
    CollectionStageApplyResponse,
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelinePreset,
    PipelineSurface,
    StageApplyResponse,
    StageViewResponse,
)

# ------------------- Preview models ------------------- #
from .preview import (
    PreviewChunk,
    PreviewCost,
    PreviewIrSummary,
    PreviewJobAccepted,
    PreviewJobResult,
    PreviewResponse,
    PreviewTraceNode,
)

# ------------------- Collection schema ops ------------------- #
from .schema_ops import (
    AddFieldOp,
    FieldOp,
    FieldPatch,
    RemoveFieldOp,
    RenameFieldOp,
    SchemaDiff,
    SchemaDiffModifiedField,
    SchemaDiffRename,
    UpdateFieldOp,
)

# ------------------- Search models ------------------- #
from .search import (
    BlockLocation,
    ChunkBrowseRequest,
    ChunkBrowseResponse,
    SearchHealthSummary,
    SearchHint,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchTarget,
)

# ------------------- Snippet models ------------------- #
from .snippets import (
    SNIPPET_FILE_EXTENSION,
    CollectionSnippet,
    SnippetImportResult,
    SnippetKind,
)

# ------------------- Storage models ------------------- #
from .storage import (
    CollectionStorageResponse,
    DocumentStorageModel,
    PostgresFootprintModel,
    QdrantFootprintModel,
    S3FootprintModel,
)

# ------------------- Trace payloads models ------------------- #
from .trace import TracePurgeResult

# ------------------- Transfers models ------------------- #
from .transfers import TransferAccepted, TransferStatus

# ------------------- Public API ------------------- #
__all__ = [
    # Shared vocabulary
    "Capability",
    "KeyPermissions",
    "FieldType",
    "FieldOrigin",
    "FieldScope",
    "SourceKind",
    "DocumentStatus",
    "EnrichmentKind",
    "EnrichmentStatus",
    # Audit
    "AuditEntry",
    "AuditPage",
    # Auth
    "CreateKeyRequest",
    "RotateKeyRequest",
    "CreatedKey",
    "KeyInfo",
    # Health
    "HealthStatus",
    "ProbeStatus",
    "ProviderProbeResult",
    "HealthVerdict",
    "IngestHealth",
    "SearchIndex",
    "SearchHealth",
    "CollectionHealthResponse",
    "CollectionListVerdict",
    "CollectionHealthSummary",
    # Collections
    "FieldSpec",
    "CollectionModel",
    "CollectionListItem",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
    "UpdateCollectionResponse",
    "FieldPatch",
    "AddFieldOp",
    "UpdateFieldOp",
    "RemoveFieldOp",
    "RenameFieldOp",
    "FieldOp",
    "SchemaDiff",
    "SchemaDiffModifiedField",
    "SchemaDiffRename",
    "BulkReingestRequest",
    "ReingestJobHandle",
    "BulkReingestAccepted",
    # Documents
    "UploadAccepted",
    "EnabledPatch",
    "DocumentEnabledResponse",
    "MetadataValuesPatch",
    "MetadataUpdateResponse",
    "DocumentView",
    # Snippets
    "SNIPPET_FILE_EXTENSION",
    "SnippetKind",
    "CollectionSnippet",
    "SnippetImportResult",
    # Corpus filter
    "DateRange",
    "DocumentFilter",
    "MetadataFilter",
    "NumberRange",
    "TextFilter",
    # Estimate
    "CollectionEstimateRequest",
    "EstimateAssumptions",
    "StageEstimate",
    "VolumeEstimate",
    "CostEstimate",
    "EstimateOverrides",
    "RateOverrides",
    "AssumptionOverrides",
    "ModelRateOverride",
    # Explorer
    "MetadataValue",
    "DocumentListItem",
    "DocumentDetail",
    "PageInfo",
    "ChunkInfo",
    "ChunkPage",
    "ChunkContext",
    "ContextChunk",
    "DocumentOutline",
    "OutlineHeading",
    "ChunkEnabledPatch",
    "BulkChunkEnabledPatch",
    "ChunkEnabledResult",
    "BulkChunkEnabledResponse",
    # IR
    "IRBlock",
    "IRTable",
    "IRFigure",
    "IREnrichment",
    "DocumentIRModel",
    "DocumentProvenance",
    # Search
    "SearchTarget",
    "SearchRequest",
    "BlockLocation",
    "SearchHint",
    "SearchHit",
    "SearchResponse",
    "ChunkBrowseRequest",
    "ChunkBrowseResponse",
    "SearchHealthSummary",
    # Jobs
    "JobStatus",
    "JobPage",
    "JobEvent",
    "JobEventPayload",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "CancelResult",
    "FailureBucket",
    "CollectionFailureBucket",
    "FailureBreakdown",
    "TimeseriesBucket",
    "JobTimeseries",
    "NewFailures",
    # Blobs
    "BlobContent",
    "CapabilitiesResponse",
    "CapabilityMatrix",
    "ServiceInfo",
    # Pipelines
    "PipelineSurface",
    "PipelineIndexResponse",
    "PipelineDesignResponse",
    "PipelinePreset",
    "InspectResponse",
    "EditResponse",
    "StageViewResponse",
    "StageApplyResponse",
    "CollectionStageApplyResponse",
    # Preview
    "PreviewIrSummary",
    "PreviewChunk",
    "PreviewCost",
    "PreviewTraceNode",
    "PreviewResponse",
    "PreviewJobAccepted",
    "PreviewJobResult",
    # Storage
    "S3FootprintModel",
    "PostgresFootprintModel",
    "QdrantFootprintModel",
    "DocumentStorageModel",
    "CollectionStorageResponse",
    # Corpus grid + bulk ops
    "DocumentSort",
    "Pagination",
    "DocumentQueryRequest",
    "DocumentGridRow",
    "DocumentQueryResponse",
    "DocumentSelector",
    "BulkDeleteResponse",
    "BulkEnabledResponse",
    "BulkReingestResponse",
    # Jobs telemetry
    "QueueDepth",
    "StageDurations",
    "CollectionCost",
    # Discovery + introspection
    "CollectionContractSchemaResponse",
    "CollectionDescription",
    "FieldGuide",
    "SearchTargetGuide",
    "WhoAmI",
    # Transfers
    "TransferAccepted",
    "TransferStatus",
    # Trace payloads
    "TracePurgeResult",
    "RebuildIndexAccepted",
]
