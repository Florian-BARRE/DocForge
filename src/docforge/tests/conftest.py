# ====== Code Summary ======
# Root test conftest. Sets required env vars BEFORE any DocForge module is imported
# (RUNTIME_CONFIG reads env at class body evaluation time), then provides common
# fixtures shared across unit and API test suites.

# ====== Standard Library Imports ======
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# ─── Preset env vars at module level ─────────────────────────────────────────
# RUNTIME_CONFIG evaluates env() calls at class-body time (i.e., import time).
# These must be set BEFORE `from config import RUNTIME_CONFIG` below, which is
# why they live here as module-level statements and NOT inside pytest_configure
# (that hook fires after conftest.py is fully imported — too late).
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("S3_SECRET_KEY", "test_secret_key")
os.environ.setdefault("LOGGING_ENABLE_CONSOLE", "false")
os.environ.setdefault("LOGGING_ENABLE_FILE", "false")

# ─── Import RUNTIME_CONFIG first (registers sys.path for libs/) ───────────────
from config import RUNTIME_CONFIG  # noqa: E402

# ─── IR model helpers (used across unit and api tests) ────────────────────────

import pytest  # noqa: E402


# ─── Async context manager mock factory ───────────────────────────────────────

def make_async_cm(return_value: object) -> MagicMock:
    """
    Build a MagicMock that works as an async context manager yielding `return_value`.

    Usage::

        mock_postgres.session = make_async_cm(mock_session)
        async with mock_postgres.session() as s:
            assert s is mock_session
    """
    @asynccontextmanager
    async def _cm() -> AsyncIterator[object]:
        yield return_value

    return _cm


# ─── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_session() -> AsyncMock:
    """A mock SQLAlchemy async session."""
    return AsyncMock()


@pytest.fixture
def mock_postgres(mock_session: AsyncMock) -> MagicMock:
    """Mock PostgresClient with a working async session() context manager."""
    mock = MagicMock()
    mock.session = make_async_cm(mock_session)
    return mock


@pytest.fixture
def mock_collection_repo() -> MagicMock:
    """Mock CollectionRepository with all public async methods."""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.list_all = AsyncMock(return_value=[])
    repo.delete = AsyncMock()
    repo.update_pipeline_version = AsyncMock()
    repo.list_document_ids = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_document_repo() -> MagicMock:
    """Mock DocumentRepository with all public async methods."""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.find_duplicate = AsyncMock(return_value=None)
    repo.update_status = AsyncMock()
    repo.update_user_meta = AsyncMock()
    repo.delete = AsyncMock()
    repo.list_by_collection = AsyncMock(return_value=[])
    repo.count_by_collection = AsyncMock(return_value=0)
    repo.count_blocks = AsyncMock(return_value=0)
    repo.get_stage_run_summary = AsyncMock(return_value={})
    repo.list_source_hashes = AsyncMock(return_value=[])
    repo.is_source_hash_shared = AsyncMock(return_value=False)
    repo.is_source_hash_used_by_other_documents = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def mock_chunk_repo() -> MagicMock:
    """Mock ChunkRepository with all public async methods."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_document = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    repo.bulk_insert = AsyncMock()
    repo.delete_by_document = AsyncMock()
    repo.count_by_document = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_block_repo() -> MagicMock:
    """Mock BlockRepository with all public async methods."""
    repo = MagicMock()
    repo.get_by_document = AsyncMock(return_value=[])
    repo.bulk_insert = AsyncMock()
    return repo


@pytest.fixture
def mock_job_repo() -> MagicMock:
    """Mock JobRepository with all public async methods."""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.list_by_document = AsyncMock(return_value=[])
    # Observability methods (Brique A)
    repo.list_jobs = AsyncMock(return_value=([], 0))
    repo.count_by_status = AsyncMock(return_value={})
    repo.count_finished_since = AsyncMock(return_value=0)
    repo.mark_running = AsyncMock()
    repo.mark_finished = AsyncMock()
    repo.update_progress = AsyncMock()
    return repo


@pytest.fixture
def mock_registry() -> MagicMock:
    """
    Mock ProviderRegistry.

    describe_stages returns an empty stage list.  build_search_pipeline returns a
    real SearchPipelineEngine wrapping whatever retrieval service it is handed, so
    search-route tests exercise the genuine engine → retrieval call path (the engine
    delegates to retrieval.search / search_debug, which the tests assert on).
    """
    from common_libs.config.pipeline.stages.search_config import SearchConfig
    from libs.search.pipeline.engine import SearchPipelineEngine

    def _build_search_pipeline(pipeline: object, retrieval: object) -> SearchPipelineEngine:
        raw_search = pipeline.get("search") if isinstance(pipeline, dict) else None
        return SearchPipelineEngine(
            config=SearchConfig.from_dict(raw_search),
            embed_provider=MagicMock(),
            retrieval=retrieval,
        )

    registry = MagicMock()
    registry.describe_stages = MagicMock(return_value={"stages": []})
    registry.build_search_pipeline = MagicMock(side_effect=_build_search_pipeline)
    return registry


@pytest.fixture
def mock_s3() -> MagicMock:
    """Mock S3Client with all public async methods."""
    s3 = MagicMock()
    # Async upload methods
    s3.upload = AsyncMock()
    s3.upload_original = AsyncMock()
    s3.upload_markdown = AsyncMock()
    # Async delete methods
    s3.delete = AsyncMock(return_value=1)
    s3.delete_prefix = AsyncMock(return_value=0)
    # Async query methods
    s3.exists = AsyncMock(return_value=True)
    s3.get_presigned_url = AsyncMock(return_value="https://example.com/presigned")
    s3.presign_get = AsyncMock(return_value="https://example.com/presigned")
    # Async download method
    s3.download = AsyncMock(return_value=b"")
    return s3


@pytest.fixture
def mock_config_repo() -> MagicMock:
    """Mock ConfigRepository with all public async methods."""
    repo = MagicMock()
    repo.list_versions = AsyncMock(return_value=[])
    repo.get_version = AsyncMock(return_value=None)
    repo.apply_config = AsyncMock()
    return repo


@pytest.fixture
def mock_metadata_indexer() -> MagicMock:
    """Mock MetadataIndexer for chunk/document re-embedding."""
    indexer = MagicMock()
    indexer.reembed_content = AsyncMock()
    indexer.sync_document_fields = AsyncMock(return_value={"synced": 0})
    return indexer


@pytest.fixture
def mock_arq() -> MagicMock:
    """Mock arq pool with enqueue_job."""
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=MagicMock(job_id="test-job-id"))
    return pool


@pytest.fixture
def mock_retrieval() -> MagicMock:
    """Mock HybridSearchService."""
    svc = MagicMock()
    svc.search = AsyncMock(return_value=[])
    return svc


@pytest.fixture
def mock_logger() -> MagicMock:
    """Silent mock logger."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger
