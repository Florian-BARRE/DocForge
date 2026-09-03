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

# ------------------- Collections models ------------------- #
from .collections import (
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
from .documents import DocumentEnabledResponse, DocumentView, EnabledPatch, UploadAccepted

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
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    DocumentDetail,
    DocumentListItem,
    MetadataValue,
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

# ------------------- IR models ------------------- #
from .ir import DocumentIRModel, IRBlock, IREnrichment, IRFigure, IRTable

# ------------------- Jobs models ------------------- #
from .jobs import (
    CancelResult,
    CollectionCost,
    JobEvent,
    JobPage,
    JobStatus,
    JobTrace,
    QueueDepth,
    StageDurations,
    WorkerActivity,
    WorkersLive,
)

# ------------------- Pipelines models ------------------- #
from .pipelines import (
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelineSurface,
    StageApplyResponse,
    StageViewResponse,
)

# ------------------- Search models ------------------- #
from .search import BlockLocation, SearchHit, SearchRequest, SearchResponse, SearchTarget

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
    "BulkReingestRequest",
    "ReingestJobHandle",
    "BulkReingestAccepted",
    # Documents
    "UploadAccepted",
    "EnabledPatch",
    "DocumentEnabledResponse",
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
    # Search
    "SearchTarget",
    "SearchRequest",
    "BlockLocation",
    "SearchHit",
    "SearchResponse",
    # Jobs
    "JobStatus",
    "JobPage",
    "JobEvent",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "CancelResult",
    # Blobs
    "BlobContent",
    # Pipelines
    "PipelineSurface",
    "PipelineIndexResponse",
    "PipelineDesignResponse",
    "InspectResponse",
    "EditResponse",
    "StageViewResponse",
    "StageApplyResponse",
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
    "WhoAmI",
    # Transfers
    "TransferAccepted",
    "TransferStatus",
]
