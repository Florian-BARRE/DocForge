# ---------------------- Shared conventions & payloads ---------------------- #
from .helpers import DatabaseHelpers
from .payloads import ChunkToggle, IngestionPayload, IRBundle, ReingestOutcome, ReingestResult
from .transfer_payloads import DocumentExportRows
from .idempotency_payloads import IdempotencyBegin, IdempotencyRecord
from .storage_footprint_payloads import (
    CollectionFootprint,
    DocumentFootprint,
    PostgresFootprint,
    QdrantFootprint,
    S3Footprint,
)

# ---------------------- Domain façades ---------------------- #
from .collections_facade import CollectionsFacade
from .documents_facade import DocumentsFacade
from .enablement_facade import EnablementFacade
from .filter_sync_facade import FilterSyncFacade
from .ingestion_facade import IngestionFacade
from .artifact_cache_facade import ArtifactCacheFacade, ArtifactCacheGcSummary
from .meta_vector_sync_facade import MetaVectorSyncFacade
from .search_facade import SearchFacade
from .jobs_facade import JobsFacade
from .auth_facade import AuthFacade
from .storage_footprint_facade import StorageFootprintFacade
from .transfer_facade import CollectionTransferFacade
from .transfer_tracker_facade import TransferTrackerFacade
from .audit_facade import AuditFacade
from .idempotency_facade import IdempotencyFacade

# ------------------- Public API ------------------- #
__all__ = [
    "DatabaseHelpers",
    "ChunkToggle",
    "IngestionPayload",
    "IRBundle",
    "ReingestOutcome",
    "ReingestResult",
    "DocumentExportRows",
    "IdempotencyBegin",
    "IdempotencyRecord",
    "CollectionFootprint",
    "DocumentFootprint",
    "S3Footprint",
    "PostgresFootprint",
    "QdrantFootprint",
    "CollectionsFacade",
    "DocumentsFacade",
    "EnablementFacade",
    "FilterSyncFacade",
    "IngestionFacade",
    "ArtifactCacheFacade",
    "ArtifactCacheGcSummary",
    "MetaVectorSyncFacade",
    "SearchFacade",
    "JobsFacade",
    "AuthFacade",
    "StorageFootprintFacade",
    "CollectionTransferFacade",
    "TransferTrackerFacade",
    "AuditFacade",
    "IdempotencyFacade",
]
