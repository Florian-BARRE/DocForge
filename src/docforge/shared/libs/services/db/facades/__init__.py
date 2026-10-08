# ---------------------- Shared conventions & payloads ---------------------- #
from .helpers import DatabaseHelpers
from .payloads import (
    AdmissionResult,
    ChunkToggle,
    ChunkToggleResult,
    CollectionUpdateResult,
    CollectionUpdateSpec,
    IngestionPayload,
    IRBundle,
    ReingestOutcome,
    ReingestResult,
)
from .reading_payloads import ChunkIndexEntry, HeadingEntry
from .transfer_payloads import DocumentExportRows
from .trace_payloads import TracePayloadRead
from .idempotency_payloads import IdempotencyBegin, IdempotencyRecord
from .storage_footprint_payloads import (
    CollectionFootprint,
    DocumentFootprint,
    PostgresFootprint,
    QdrantFootprint,
    S3Footprint,
)

# ---------------------- Domain façades ---------------------- #
from .collection_alias_facade import AliasAuthorizer, CollectionAliasFacade
from .collection_alias_payloads import (
    CollectionAliasConflictError,
    CollectionAliasInUseError,
    CollectionAliasedError,
    CollectionAliasNameClashError,
    CollectionAliasTargetMissingError,
    CollectionAliasWrite,
)
from .collection_config_writer import CollectionConfigWriter, ConfigVersionConflictError
from .config_history_facade import ConfigHistoryFacade
from .config_history_payloads import ConfigAuthor, ConfigVersionPage
from .collections_facade import CollectionsFacade, DuplicateCollectionNameError
from .documents_facade import DocumentsFacade
from .enablement_facade import EnablementFacade
from .filter_sync_facade import FilterSyncFacade
from .index_state_facade import IndexStateFacade
from .index_rebuild_facade import IndexRebuildFacade
from .index_rebuild_payloads import (
    AbortProbe,
    CollectionBusyError,
    IndexRebuildActiveError,
    RebuildCancelledError,
    RebuildReconcileResult,
    RebuildUnsupportedError,
    StoreCopyResult,
)
from .rebuild_guard import RebuildGuard
from .content_sparse_reencoder import ContentSparseReencoder
from .store_rebuild_facade import StoreRebuildFacade
from .ingestion_facade import IngestionFacade
from .ir_bundle_adapter import IRBundleAdapter
from .replay_persist_facade import ReplayPersistFacade
from .replay_source_facade import ReplaySourceFacade
from .artifact_cache_facade import ArtifactCacheFacade, ArtifactCacheGcSummary
from .meta_vector_sync_facade import MetaVectorSyncFacade
from .metadata_edit_facade import (
    MetadataEditFacade,
    MetadataEditNotFoundError,
    MetadataEditResult,
    MetadataValidationError,
)
from .schema_change_facade import FieldPurgeOutcome, SchemaChangeFacade
from .search_facade import SearchFacade
from .jobs_facade import JobsFacade
from .trace_payload_facade import TracePayloadFacade
from .auth_facade import AuthFacade
from .storage_footprint_facade import StorageFootprintFacade
from .transfer_facade import CollectionTransferFacade
from .transfer_tracker_facade import TransferTrackerFacade
from .audit_facade import AuditFacade
from .idempotency_facade import IdempotencyFacade
from .metadata_value_resolver import MetadataValueResolver

# ------------------- Public API ------------------- #
__all__ = [
    "AliasAuthorizer",
    "CollectionAliasFacade",
    "CollectionAliasConflictError",
    "CollectionAliasInUseError",
    "CollectionAliasedError",
    "CollectionAliasNameClashError",
    "CollectionAliasTargetMissingError",
    "CollectionAliasWrite",
    "ConfigHistoryFacade",
    "ConfigAuthor",
    "ConfigVersionPage",
    "IndexRebuildFacade",
    "AbortProbe",
    "CollectionBusyError",
    "IndexRebuildActiveError",
    "RebuildCancelledError",
    "RebuildUnsupportedError",
    "RebuildReconcileResult",
    "StoreCopyResult",
    "RebuildGuard",
    "StoreRebuildFacade",
    "ContentSparseReencoder",
    "FieldPurgeOutcome",
    "SchemaChangeFacade",
    "DatabaseHelpers",
    "AdmissionResult",
    "ChunkToggle",
    "ChunkToggleResult",
    "CollectionUpdateResult",
    "CollectionUpdateSpec",
    "IngestionPayload",
    "IRBundle",
    "IRBundleAdapter",
    "ReplayPersistFacade",
    "ReplaySourceFacade",
    "ReingestOutcome",
    "ReingestResult",
    "ChunkIndexEntry",
    "HeadingEntry",
    "DocumentExportRows",
    "TracePayloadRead",
    "IdempotencyBegin",
    "IdempotencyRecord",
    "CollectionFootprint",
    "DocumentFootprint",
    "S3Footprint",
    "PostgresFootprint",
    "QdrantFootprint",
    "CollectionConfigWriter",
    "CollectionsFacade",
    "ConfigVersionConflictError",
    "DuplicateCollectionNameError",
    "DocumentsFacade",
    "EnablementFacade",
    "FilterSyncFacade",
    "IndexStateFacade",
    "IngestionFacade",
    "ArtifactCacheFacade",
    "ArtifactCacheGcSummary",
    "MetaVectorSyncFacade",
    "MetadataEditFacade",
    "MetadataEditNotFoundError",
    "MetadataEditResult",
    "MetadataValidationError",
    "SearchFacade",
    "JobsFacade",
    "TracePayloadFacade",
    "AuthFacade",
    "StorageFootprintFacade",
    "CollectionTransferFacade",
    "TransferTrackerFacade",
    "AuditFacade",
    "IdempotencyFacade",
    "MetadataValueResolver",
]
