# ====== Code Summary ======
# StageDeps frozen dataclass — bundles the shared infrastructure dependencies
# passed to the dynamic engine hooks (WorkerEngineHooks) and the cache/persist
# helpers, avoiding repeated kwargs at every call site.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.storage.postgres.client import PostgresClient
    from common_libs.storage.postgres.repositories import (
        BlockRepository,
        ChunkRepository,
        DocumentRepository,
    )
    from common_libs.storage.s3.client import S3Client
    from common_libs.pipeline.caches.node_cache import NodeCache
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache


@dataclass(frozen=True)
class StageDeps:
    """
    Frozen container of shared infrastructure dependencies for the dynamic engine.

    Built once by ``DynamicStageEngine`` and handed to ``WorkerEngineHooks`` + the cache/persist
    helpers, so individual calls do not need to accept these as repeated keyword arguments.

    Attributes:
        s3 (S3Client): SeaweedFS object store client.
        postgres (PostgresClient): Postgres session factory.
        node_cache (NodeCache): Merkle-DAG node cache (stage_run table).
        provider_cache (ProviderCallCache): Cross-document provider-call cache.
        document_repo (DocumentRepository): Document status update operations.
        block_repo (BlockRepository): IR block persistence operations.
        chunk_repo (ChunkRepository | None): Chunk persistence operations (P4); None when disabled.
    """

    s3: S3Client
    postgres: PostgresClient
    node_cache: NodeCache
    provider_cache: ProviderCallCache
    document_repo: DocumentRepository
    block_repo: BlockRepository
    chunk_repo: ChunkRepository | None
