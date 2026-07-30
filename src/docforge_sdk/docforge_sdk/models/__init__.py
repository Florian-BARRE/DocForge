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

# ------------------- Auth models ------------------- #
from .auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest

# ------------------- Blobs models ------------------- #
from .blobs import BlobContent

# ------------------- Collections models ------------------- #
from .collections import (
    CollectionModel,
    CreateCollectionRequest,
    FieldSpec,
    UpdateCollectionRequest,
)

# ------------------- Documents models ------------------- #
from .documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted

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
from .health import HealthStatus

# ------------------- IR models ------------------- #
from .ir import DocumentIRModel, IRBlock, IREnrichment, IRFigure, IRTable

# ------------------- Jobs models ------------------- #
from .jobs import JobEvent, JobStatus, JobTrace, WorkerActivity, WorkersLive

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
from .search import SearchHit, SearchRequest, SearchResponse, SearchTarget

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
    # Documents
    "UploadAccepted",
    "EnabledPatch",
    "DocumentEnabledResponse",
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
    "SearchHit",
    "SearchResponse",
    # Jobs
    "JobStatus",
    "JobEvent",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
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
]
