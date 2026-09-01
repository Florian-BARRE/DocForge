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

# ------------------- Auth models ------------------- #
from .models.auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest

# ------------------- Blobs models ------------------- #
from .models.blobs import BlobContent

# ------------------- Collections models ------------------- #
from .models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionModel,
    CreateCollectionRequest,
    FieldSpec,
    ReingestJobHandle,
    UpdateCollectionRequest,
)

# ------------------- Documents models ------------------- #
from .models.documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted

# ------------------- Explorer models ------------------- #
from .models.explorer import (
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
from .models.health import HealthStatus

# ------------------- IR models ------------------- #
from .models.ir import DocumentIRModel, IRBlock, IREnrichment, IRFigure, IRTable

# ------------------- Jobs models ------------------- #
from .models.jobs import (
    CancelResult,
    JobEvent,
    JobPage,
    JobStatus,
    JobTrace,
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

# ------------------- Search models ------------------- #
from .models.search import BlockLocation, SearchHit, SearchRequest, SearchResponse, SearchTarget

# ------------------- Storage models ------------------- #
from .models.storage import (
    CollectionStorageResponse,
    DocumentStorageModel,
    PostgresFootprintModel,
    QdrantFootprintModel,
    S3FootprintModel,
)

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
    "BulkReingestRequest",
    "ReingestJobHandle",
    "BulkReingestAccepted",
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
    # Transfers
    "TransferAccepted",
    "TransferStatus",
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
