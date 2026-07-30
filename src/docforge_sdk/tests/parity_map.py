# ====== Code Summary ======
# Shared source of truth for the model↔OpenAPI parity checks: the mapping from each OpenAPI
# component-schema NAME to the SDK model that mirrors it, plus the deliberately-exempt models with
# their reasons. Imported by BOTH the offline parity test (diff vs a committed snapshot) and the live
# parity test (diff vs a running API's /openapi.json), so the two guards never drift apart. This is a
# helper module, not a test module — pytest does not collect it.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
from docforge_sdk.models.auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest
from docforge_sdk.models.collections import (
    CollectionModel,
    CreateCollectionRequest,
    FieldSpec,
    UpdateCollectionRequest,
)
from docforge_sdk.models.documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted
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
from docforge_sdk.models.ir import DocumentIRModel, IRBlock, IREnrichment, IRFigure, IRTable
from docforge_sdk.models.jobs import JobEvent, JobStatus, JobTrace, WorkerActivity, WorkersLive
from docforge_sdk.models.pipelines import (
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelineSurface,
    StageApplyResponse,
    StageViewResponse,
)
from docforge_sdk.models.search import SearchHit, SearchRequest, SearchResponse, SearchTarget

# Maps the OpenAPI component-schema NAME to the SDK model that mirrors it. A handful of SDK classes
# drop the backend's "Model" suffix (FieldSpec, SearchTarget, SearchHit), so the key is authoritative.
MODELS: dict[str, type[BaseModel]] = {
    # Auth
    "CreateKeyRequest": CreateKeyRequest,
    "RotateKeyRequest": RotateKeyRequest,
    "CreatedKey": CreatedKey,
    "KeyInfo": KeyInfo,
    # Collections
    "FieldSpecModel": FieldSpec,
    "CollectionModel": CollectionModel,
    "CreateCollectionRequest": CreateCollectionRequest,
    "UpdateCollectionRequest": UpdateCollectionRequest,
    # Documents
    "UploadAccepted": UploadAccepted,
    "EnabledPatch": EnabledPatch,
    "DocumentEnabledResponse": DocumentEnabledResponse,
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
    "IREnrichment": IREnrichment,
    "DocumentIRModel": DocumentIRModel,
    # Search
    "SearchTargetModel": SearchTarget,
    "SearchRequest": SearchRequest,
    "SearchHitModel": SearchHit,
    "SearchResponse": SearchResponse,
    # Jobs
    "JobStatus": JobStatus,
    "JobEvent": JobEvent,
    "JobTrace": JobTrace,
    "WorkerActivity": WorkerActivity,
    "WorkersLive": WorkersLive,
    # Pipelines (opaque graph JSON typed as dicts, but property names + required still 1:1)
    "PipelineSurface": PipelineSurface,
    "PipelineIndexResponse": PipelineIndexResponse,
    "PipelineDesignResponse": PipelineDesignResponse,
    "InspectResponse": InspectResponse,
    "EditResponse": EditResponse,
    "StageViewResponse": StageViewResponse,
    "StageApplyResponse": StageApplyResponse,
}

# SDK models deliberately WITHOUT a 1:1 OpenAPI schema, each with the reason it is skipped.
SKIPPED: dict[str, str] = {
    "HealthStatus": "health route is registered with include_in_schema=False (absent from the schema).",
    "BlobContent": "SDK-only wrapper — the blobs endpoint streams raw bytes, not a JSON schema.",
}

__all__ = ["MODELS", "SKIPPED"]
