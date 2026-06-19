# ====== Code Summary ======
# StageDeps frozen dataclass — bundles the shared infrastructure dependencies
# passed to S012Runner and S456Runner.  A single frozen instance is created by
# StageEngine.__init__ and shared across all runner objects, avoiding repeated
# kwargs at every call site.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.storage.postgres.client import PostgresClient
    from libs.storage.postgres.repositories import (
        BlockRepository,
        ChunkRepository,
        DocumentRepository,
    )
    from libs.storage.s3.client import S3Client
    from libs.pipeline.caches.node_cache import NodeCache
    from libs.pipeline.caches.provider_cache import ProviderCallCache


@dataclass(frozen=True)
class StageDeps:
    """
    Frozen container of shared infrastructure dependencies for stage runners.

    Passed once to S012Runner and S456Runner at construction time so individual
    run methods do not need to accept these as repeated keyword arguments.

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
