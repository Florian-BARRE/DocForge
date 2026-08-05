# ---------------------- Declarative base & mixins ---------------------- #
from .base import NAMING_CONVENTION, Base, CreatedAtMixin, TimestampedMixin, UUIDPrimaryKey

# Importing every domain here registers all tables on Base.metadata (what Alembic autogenerate
# compares against). Tables reference each other by foreign key only — no ORM relationships — so
# there are no cross-table imports to resolve.

# ---------------------- Collections ---------------------- #
from .collections import Collection, MetadataField

# ---------------------- Documents ---------------------- #
from .documents import Document, DocumentMetadata, DocumentStatus, Page, SourceKind

# ---------------------- Blobs ---------------------- #
from .blobs import Blob, BlobKind

# ---------------------- IR (parse + enrich) ---------------------- #
from .ir import (
    AttemptStatus,
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    EnrichmentAttempt,
    EnrichmentKind,
    EnrichmentStatus,
)

# ---------------------- Chunks ---------------------- #
from .chunks import Chunk, ChunkBlock, ChunkMetadata, EntityMention

# ---------------------- Observability ---------------------- #
from .observability import ConfigVersion, Job, JobStageEvent, JobStatus, WorkerHeartbeat

# ---------------------- Authentication ---------------------- #
from .authentication import ApiKey, AppUser, UserRole

# ------------------- Public API ------------------- #
__all__ = [
    # base
    "Base",
    "TimestampedMixin",
    "CreatedAtMixin",
    "UUIDPrimaryKey",
    "NAMING_CONVENTION",
    # collections
    "Collection",
    "MetadataField",
    # documents
    "Document",
    "DocumentStatus",
    "SourceKind",
    "Page",
    "DocumentMetadata",
    # blobs
    "Blob",
    "BlobKind",
    # ir
    "Block",
    "BlockTable",
    "BlockFigure",
    "BlockEnrichment",
    "EnrichmentKind",
    "EnrichmentStatus",
    "EnrichmentAttempt",
    "AttemptStatus",
    # chunks
    "Chunk",
    "ChunkBlock",
    "ChunkMetadata",
    "EntityMention",
    # observability
    "Job",
    "JobStatus",
    "JobStageEvent",
    "WorkerHeartbeat",
    "ConfigVersion",
    # authentication
    "AppUser",
    "UserRole",
    "ApiKey",
]
