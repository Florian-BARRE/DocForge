# ====== Code Summary ======
# Typed service locator for DocForge. All shared services are accessed via CONTEXT —
# never imported directly in route files.  Values are assigned in entrypoint.py at startup.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from arq import ArqRedis
from loggerplusplus import LoggerPlusPlus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from backend.libs.admission import ResourceAdmitter
from common_libs.observability.events import EventBroadcaster, EventPublisher
from common_libs.observability.heartbeat import HeartbeatReader
from backend.libs.observability.queue import QueueIntrospector
from common_libs.pipeline.assembly import ProviderRegistry
from common_libs.pipeline.caches.node_cache import NodeCache
from common_libs.pipeline.caches.provider_cache import ProviderCallCache
from common_libs.providers.converter import GotenbergConverter
from common_libs.providers.device_manager import DeviceManager
from backend.libs.search.hybrid.service import HybridSearchService
from backend.libs.search.metadata_indexer.indexer import MetadataIndexer
from backend.libs.auth import AuthService
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.repositories import (
    ApiKeyRepository,
    BlockRepository,
    ChunkRepository,
    CollectionGrantRepository,
    CollectionRepository,
    ConfigRepository,
    DocumentRepository,
    JobRepository,
    UserRepository,
)
from common_libs.storage.qdrant.client import QdrantStorageClient
from common_libs.storage.s3.client import S3Client


class CONTEXT:
    """
    Shared application context — typed service locator.

    Type annotations only.  All values are assigned at startup in entrypoint.py.
    Access via CONTEXT.<attribute> anywhere in the codebase.
    Never instantiate this class.
    """

    # ── Core infrastructure ──────────────────────────────────────────────────
    logger: LoggerPlusPlus
    RUNTIME_CONFIG: type[RUNTIME_CONFIG]

    # ── Storage ─────────────────────────────────────────────────────────────
    postgres: PostgresClient
    s3: S3Client                        # SeaweedFS S3-compatible object store
    arq_pool: ArqRedis                  # arq Redis connection pool (enqueue jobs)
    qdrant: QdrantStorageClient | None   # Qdrant vector store (P4, None when unreachable at startup)
    retrieval: HybridSearchService | None  # hybrid search service (P5, None when Qdrant unavailable)
    metadata_indexer: MetadataIndexer | None  # targeted metadata→index sync (None when Qdrant unavailable)

    # ── Providers ────────────────────────────────────────────────────────────
    device_manager: DeviceManager
    converter: GotenbergConverter

    # ── Repositories ─────────────────────────────────────────────────────────
    collection_repo: CollectionRepository
    config_repo: ConfigRepository
    document_repo: DocumentRepository
    block_repo: BlockRepository
    chunk_repo: ChunkRepository
    job_repo: JobRepository

    # ── Auth (authentication + per-collection authorization) ──────────────────
    user_repo: UserRepository
    api_key_repo: ApiKeyRepository
    grant_repo: CollectionGrantRepository
    auth_service: AuthService

    # ── Pipeline (P2 / P3 / P4) ─────────────────────────────────────────────
    node_cache: NodeCache
    provider_cache: ProviderCallCache
    registry: ProviderRegistry  # resolves per-run PipelineConfig → concrete stages

    # ── Observability (Brique A) ─────────────────────────────────────────────
    # Read-only views over Redis telemetry, all sharing the arq_pool connection.
    queue_introspector: QueueIntrospector   # arq queue depth + per-job arq status
    heartbeat_reader: HeartbeatReader       # live worker heartbeats
    event_publisher: EventPublisher         # publish monitoring events (also consumed in brique C)

    # ── Real-time streaming (Brique C) ───────────────────────────────────────
    # Subscribes once to the events channel and fans out to SSE clients (own Redis connection).
    event_broadcaster: EventBroadcaster

    # ── Resource admission (Brique D) ────────────────────────────────────────
    # Runtime back-pressure gate on enqueue (queue depth / in-flight).
    resource_admitter: ResourceAdmitter

    # ── Runtime state ────────────────────────────────────────────────────────
    active_tasks: dict[str, Any]
