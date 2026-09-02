# ====== Code Summary ======
# Database — THE single point of contact with the data layer. It owns the three store clients
# (Postgres = tabular truth, Qdrant = vectors, S3 = blobs) and exposes every operation through its
# domain façades: `db.collections`, `db.ingestion`, `db.documents`, `db.search`,
# `db.jobs`, `db.auth`. Nothing outside this object touches a client or an api directly — the
# cross-store coherence rules (write PG-first, delete Qdrant-first, reference-filtered blob purge)
# are encoded once, inside the façades it composes.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.qdrant import QdrantClient
from shared_libs.services.db.s3 import S3Client

# ====== Local Project Imports ======
from .facades import (
    ArtifactCacheFacade,
    AuditFacade,
    AuthFacade,
    CollectionsFacade,
    CollectionTransferFacade,
    DocumentsFacade,
    EnablementFacade,
    FilterSyncFacade,
    IdempotencyFacade,
    IngestionFacade,
    JobsFacade,
    MetaVectorSyncFacade,
    SearchFacade,
    StorageFootprintFacade,
    TransferTrackerFacade,
)


class Database(LoggerClass):
    """
    The unified data layer — one object, three stores, seven domain façades.

    Attributes:
        collections (CollectionsFacade): Collection lifecycle (create fail-fast, config, delete).
        ingestion (IngestionFacade): The worker's persistence path (admit, blobs, save, index).
        artifact_cache (ArtifactCacheFacade): The per-collection stage-artifact cache (hook I/O + GC).
        documents (DocumentsFacade): Reading, inspection (raw/enriched IR, chunks), deletion.
        enablement (EnablementFacade): Reversible enable/disable of documents/chunks (flag + payload).
        filters (FilterSyncFacade): Denormalise document-scope filterable metadata onto chunk points.
        meta_vectors (MetaVectorSyncFacade): Populate document-scope metadata named vectors on points.
        search (SearchFacade): Hybrid filtered search + Postgres hydration.
        jobs (JobsFacade): Ingestion job lifecycle + stage timeline.
        auth (AuthFacade): User accounts + API keys.
        storage (StorageFootprintFacade): On-demand material footprint (S3 + Postgres + Qdrant).
        transfer (CollectionTransferFacade): The collection export/import store gateway (streamed
            reads, id-preserving restore writes, rollback).
        transfer_tracker (TransferTrackerFacade): The collection-transfer tracking-row lifecycle.
        audit (AuditFacade): The append-only audit trail (record, keyset read, retention prune).
        idempotency (IdempotencyFacade): The Stripe-style idempotency store (guard insert, cache
            complete/drop, expiry prune) backing the app's Idempotency-Key middleware.
    """

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth store.
            qdrant (QdrantClient): The vector store.
            s3 (S3Client): The blob store.
        """
        LoggerClass.__init__(self)
        # 1. Keep the clients for lifecycle management (close()).
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3
        # 2. Wire each domain façade with exactly the stores it needs.
        self.collections = CollectionsFacade(postgres, qdrant, s3)
        self.ingestion = IngestionFacade(postgres, qdrant, s3)
        self.artifact_cache = ArtifactCacheFacade(postgres, s3)
        self.documents = DocumentsFacade(postgres, qdrant, s3)
        self.enablement = EnablementFacade(postgres, qdrant)
        self.filters = FilterSyncFacade(postgres, qdrant)
        self.meta_vectors = MetaVectorSyncFacade(postgres, qdrant)
        self.search = SearchFacade(postgres, qdrant)
        self.jobs = JobsFacade(postgres)
        self.auth = AuthFacade(postgres)
        self.storage = StorageFootprintFacade(postgres, qdrant)
        self.transfer = CollectionTransferFacade(postgres, qdrant, s3)
        self.transfer_tracker = TransferTrackerFacade(postgres)
        self.audit = AuditFacade(postgres)
        self.idempotency = IdempotencyFacade(postgres)
        self.logger.info(f"Database facade ready (postgres + qdrant + s3)")

    async def ensure_object_store(self) -> None:
        """Provision the blob bucket if missing (idempotent) — call once at startup."""
        await self._s3.ensure_bucket()

    async def close(self) -> None:
        """Release every store connection — call on application shutdown."""
        await self._postgres.dispose()
        await self._qdrant.close()
        await self._s3.close()
        self.logger.info(f"Database facade closed")


__all__ = ["Database"]
