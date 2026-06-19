# ====== Code Summary ======
# Typed service locator for DocForge. All shared services are accessed via CONTEXT —
# never imported directly in route files.  Values are assigned in entrypoint.py at startup.

# ====== Standard Library Imports ======
from typing import Any, Type

# ====== Third-Party Library Imports ======
from arq import ArqRedis
from loggerplusplus import LoggerPlusPlus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from libs.engine.engine import StageEngine
from libs.engine.node_cache import NodeCache
from libs.engine.provider_cache import ProviderCallCache
from libs.capabilities.converter import GotenbergConverter
from libs.capabilities.device_manager import DeviceManager
from libs.capabilities.parser import DoclingBackend
from libs.capabilities.registry import ProviderRegistry
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.postgres.repositories import (
    BlockRepository,
    ChunkRepository,
    CollectionRepository,
    ConfigRepository,
    DocumentRepository,
    JobRepository,
)
from libs.core.metadata.indexer import MetadataIndexer
from libs.data.retrieval.hybrid_search import HybridSearchService
from libs.data.storage.qdrant.client import QdrantStorageClient
from libs.data.storage.s3.client import S3Client


class CONTEXT:
    """
    Shared application context — typed service locator.

    Type annotations only.  All values are assigned at startup in entrypoint.py.
    Access via CONTEXT.<attribute> anywhere in the codebase.
    Never instantiate this class.
    """

    # ── Core infrastructure ──────────────────────────────────────────────────
    logger: LoggerPlusPlus
    RUNTIME_CONFIG: Type[RUNTIME_CONFIG]

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
    parser: DoclingBackend

    # ── Repositories ─────────────────────────────────────────────────────────
    collection_repo: CollectionRepository
    config_repo: ConfigRepository
    document_repo: DocumentRepository
    block_repo: BlockRepository
    chunk_repo: ChunkRepository
    job_repo: JobRepository

    # ── Pipeline (P2 / P3 / P4) ─────────────────────────────────────────────
    node_cache: NodeCache
    provider_cache: ProviderCallCache
    registry: ProviderRegistry  # resolves per-run PipelineConfig → concrete stages
    stage_engine: StageEngine   # s6 is None when Qdrant is unreachable

    # ── Runtime state ────────────────────────────────────────────────────────
    active_tasks: dict[str, Any]
