# ------------------- Exceptions ------------------- #
from ._exceptions import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthError,
    ConflictError,
    DocForgeError,
    NotFoundError,
    UnprocessableError,
)
from ._version import __version__

# ------------------- Clients ------------------- #
from .client import AsyncClient, Client

# ------------------- Shared vocabulary ------------------- #
from .models._shared import (
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
from .models.audit import AuditEntry, AuditPage

# ------------------- Auth models ------------------- #
from .models.auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest

# ------------------- Blobs models ------------------- #
from .models.blobs import BlobContent

# ------------------- Capabilities models ------------------- #
from .models.capabilities import CapabilitiesResponse, CapabilityMatrix, ServiceInfo

# ------------------- Collections models ------------------- #
from .models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionModel,
    CreateCollectionRequest,
    FieldSpec,
    ReingestJobHandle,
    UpdateCollectionRequest,
    UpdateCollectionResponse,
)

# ------------------- Documents models ------------------- #
from .models.documents import (
    DocumentEnabledResponse,
    EnabledPatch,
    MetadataUpdateResponse,
    MetadataValuesPatch,
    UploadAccepted,
)

# ------------------- Estimate models ------------------- #
from .models.estimate import (
    CollectionEstimateRequest,
    CostEstimate,
    EstimateAssumptions,
    StageEstimate,
    VolumeEstimate,
)

# ------------------- Explorer models ------------------- #
from .models.explorer import (
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
from .models.health import HealthStatus

# ------------------- Index rebuild models ------------------- #
from .models.index_rebuild import RebuildIndexAccepted

# ------------------- IR models ------------------- #
from .models.ir import (
    DocumentIRModel,
    DocumentProvenance,
    IRBlock,
    IREnrichment,
    IRFigure,
    IRTable,
)

# ------------------- Jobs models ------------------- #
from .models.jobs import (
    CancelResult,
    FailureBreakdown,
    JobEvent,
    JobEventPayload,
    JobPage,
    JobStatus,
    JobTimeseries,
    JobTrace,
    NewFailures,
    WorkerActivity,
    WorkersLive,
)

# ------------------- Pipelines models ------------------- #
from .models.pipelines import (
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelineSurface,
    StageApplyResponse,
    StageViewResponse,
)

# ------------------- Preview models ------------------- #
from .models.preview import (
    PreviewChunk,
    PreviewCost,
    PreviewIrSummary,
    PreviewJobAccepted,
    PreviewJobResult,
    PreviewResponse,
    PreviewTraceNode,
)

# ------------------- Collection schema ops ------------------- #
from .models.schema_ops import (
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
from .models.search import (
    BlockLocation,
    ChunkBrowseRequest,
    ChunkBrowseResponse,
    SearchHealthSummary,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchTarget,
)

# ------------------- Storage models ------------------- #
from .models.storage import (
    CollectionStorageResponse,
    DocumentStorageModel,
    PostgresFootprintModel,
    QdrantFootprintModel,
    S3FootprintModel,
)

# ------------------- Trace payloads models ------------------- #
from .models.trace import TracePurgeResult

# ------------------- Transfers models ------------------- #
from .models.transfers import TransferAccepted, TransferStatus

# ------------------- Public API ------------------- #
__all__ = [
    "__version__",
    # Clients
    "AsyncClient",
    "Client",
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
    # Collections
    "FieldSpec",
    "CollectionModel",
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
    # Estimate
    "CollectionEstimateRequest",
    "EstimateAssumptions",
    "StageEstimate",
    "VolumeEstimate",
    "CostEstimate",
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
    "SearchHit",
    "SearchResponse",
    "ChunkBrowseRequest",
    "ChunkBrowseResponse",
    "SearchHealthSummary",
    # Preview
    "PreviewIrSummary",
    "PreviewChunk",
    "PreviewCost",
    "PreviewTraceNode",
    "PreviewResponse",
    "PreviewJobAccepted",
    "PreviewJobResult",
    # Jobs
    "JobStatus",
    "JobPage",
    "JobEvent",
    "JobEventPayload",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "CancelResult",
    "FailureBreakdown",
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
    # Transfers
    "TransferAccepted",
    "TransferStatus",
    # Trace payloads
    "TracePurgeResult",
    "RebuildIndexAccepted",
    # Exceptions
    "DocForgeError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "AuthError",
    "NotFoundError",
    "ConflictError",
    "UnprocessableError",
]
