# ====== Code Summary ======
# API test conftest — provides the httpx AsyncClient pointed at a test FastAPI app
# with all CONTEXT attributes replaced by mocks.  No real database / S3 / Redis.

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

# ====== Internal Project Imports ======
# RUNTIME_CONFIG is already imported in root conftest.py which runs first.
from backend.context import CONTEXT
from backend.libs.admission import ResourceAdmitter
from common_libs.config.validation import ConfigValidator
from backend.routers import (
    access_router,
    auth_router,
    chunks_router,
    collection_router,
    config_router,
    discovery_router,
    document_router,
    files_router,
    health_router,
    jobs_router,
    limits_router,
    monitoring_router,
    pages_router,
    search_router,
    users_router,
)


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """No-op lifespan: skips all real service startup/shutdown for tests."""
    yield


def _make_test_app() -> FastAPI:
    """
    Build a minimal FastAPI app for testing.

    Uses a no-op lifespan so no real Postgres / S3 / Redis connections are made.
    All services are injected via CONTEXT monkeypatching in the fixture below.
    """
    app = FastAPI(title="DocForge Test", lifespan=_noop_lifespan)
    V1 = "/api/v1"
    COL = f"{V1}/collections"
    DOC = f"{COL}/{{collection_id}}/documents"
    app.include_router(router=health_router,    prefix=f"{V1}/health")
    app.include_router(router=auth_router,      prefix=f"{V1}/auth")
    app.include_router(router=users_router,     prefix=f"{V1}/users")
    app.include_router(router=discovery_router, prefix=f"{V1}/discovery")
    app.include_router(router=collection_router,   prefix=COL)
    app.include_router(router=config_router,     prefix=f"{COL}/{{collection_id}}/config")
    app.include_router(router=limits_router,      prefix=f"{COL}/{{collection_id}}/limits")
    app.include_router(router=access_router,     prefix=f"{COL}/{{collection_id}}/access")
    app.include_router(router=document_router,   prefix=DOC)
    app.include_router(router=search_router,     prefix=DOC)
    app.include_router(router=files_router,      prefix=f"{DOC}/{{document_id}}")
    app.include_router(router=chunks_router,     prefix=f"{DOC}/{{document_id}}/chunks")
    app.include_router(router=pages_router,      prefix=f"{DOC}/{{document_id}}/pages")
    app.include_router(router=jobs_router,       prefix=f"{V1}/jobs")
    app.include_router(router=monitoring_router, prefix=f"{V1}/monitoring")
    return app


# Build once — routes are stateless (all state lives in CONTEXT)
_test_app = _make_test_app()


@pytest.fixture(autouse=True)
def inject_context(
    mock_postgres: MagicMock,
    mock_collection_repo: MagicMock,
    mock_document_repo: MagicMock,
    mock_chunk_repo: MagicMock,
    mock_block_repo: MagicMock,
    mock_job_repo: MagicMock,
    mock_s3: MagicMock,
    mock_arq: MagicMock,
    mock_retrieval: MagicMock,
    mock_registry: MagicMock,
    mock_logger: MagicMock,
    mock_config_repo: MagicMock,
    mock_user_repo: MagicMock,
    mock_api_key_repo: MagicMock,
    mock_grant_repo: MagicMock,
    mock_auth_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Inject mock services into the static CONTEXT before every API test.

    Uses monkeypatch so all attributes are restored after each test, preventing
    state leakage between test functions.
    """
    # raising=False: CONTEXT is a static class with type annotations only (no real attribute
    # values until entrypoint.py runs), so monkeypatch must be allowed to create new attrs.
    monkeypatch.setattr(CONTEXT, "logger", mock_logger, raising=False)
    monkeypatch.setattr(
        CONTEXT,
        "RUNTIME_CONFIG",
        # AUTH_ENABLED=False activates the kill-switch in require_principal so the existing
        # test suite needs no Authorization headers — a synthetic root principal is injected.
        MagicMock(FASTAPI_DEBUG_MODE=False, APP_VERSION="0.1.0-test", AUTH_ENABLED=False),
        raising=False,
    )
    monkeypatch.setattr(CONTEXT, "postgres", mock_postgres, raising=False)
    monkeypatch.setattr(CONTEXT, "s3", mock_s3, raising=False)
    monkeypatch.setattr(CONTEXT, "arq_pool", mock_arq, raising=False)
    monkeypatch.setattr(CONTEXT, "qdrant", None, raising=False)
    monkeypatch.setattr(CONTEXT, "retrieval", mock_retrieval, raising=False)
    monkeypatch.setattr(CONTEXT, "registry", mock_registry, raising=False)
    # The search route calls the module-level build_search_pipeline (relocated out of the
    # registry into backend.libs.search.builder). Patch it to assemble a real
    # SearchPipelineEngine around the mock retrieval, so route tests exercise the genuine
    # engine → retrieval path without building real embed providers.
    from common_libs.config.pipeline.stages.search_config import SearchConfig
    from backend.libs.search.pipeline.engine import SearchPipelineEngine

    def _fake_build_search_pipeline(pipeline_dict: object, retrieval: object, runtime_config: object):
        raw_search = pipeline_dict.get("search") if isinstance(pipeline_dict, dict) else None
        return SearchPipelineEngine(
            config=SearchConfig.from_dict(raw_search),
            embed_provider=MagicMock(),
            retrieval=retrieval,
        )

    monkeypatch.setattr(
        "backend.routers.collections.documents.search.router.build_search_pipeline",
        _fake_build_search_pipeline,
        raising=True,
    )
    mock_dm = MagicMock()
    mock_dm.gpu_available = False
    mock_dm.gpu_name = None
    mock_dm.device = "cpu"
    mock_dm.cuda_version = None
    monkeypatch.setattr(CONTEXT, "device_manager", mock_dm, raising=False)
    monkeypatch.setattr(CONTEXT, "collection_repo", mock_collection_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "config_repo", mock_config_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "document_repo", mock_document_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "block_repo", mock_block_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "chunk_repo", mock_chunk_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "job_repo", mock_job_repo, raising=False)
    # Auth repos + service — auth is disabled by default (AUTH_ENABLED=False above), so these
    # mocks are never actually called by the existing tests. They are wired so that routes that
    # declare auth dependencies (require_principal etc.) can import without AttributeError, and
    # so per-test auth-on tests can override individual mocks as needed.
    monkeypatch.setattr(CONTEXT, "user_repo", mock_user_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "api_key_repo", mock_api_key_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "grant_repo", mock_grant_repo, raising=False)
    monkeypatch.setattr(CONTEXT, "auth_service", mock_auth_service, raising=False)
    monkeypatch.setattr(CONTEXT, "stage_engine", MagicMock(), raising=False)
    # Observability handles (Brique A) — async views; tests that exercise monitoring
    # override these with AsyncMock return values as needed.
    monkeypatch.setattr(CONTEXT, "queue_introspector", MagicMock(), raising=False)
    monkeypatch.setattr(CONTEXT, "heartbeat_reader", MagicMock(), raising=False)
    monkeypatch.setattr(CONTEXT, "event_publisher", MagicMock(), raising=False)
    # Resource admitter (Brique D) — disabled by default so ingest tests are never throttled;
    # the 429/409 tests override this with an AsyncMock returning a reject decision.
    monkeypatch.setattr(
        CONTEXT,
        "resource_admitter",
        ResourceAdmitter(enabled=False, max_queue_depth=0, max_in_flight_global=0),
        raising=False,
    )
    # node_cache.invalidate_document is awaited in DocumentOps.reingest — must be AsyncMock.
    _mock_nc = MagicMock()
    _mock_nc.invalidate_document = AsyncMock()
    monkeypatch.setattr(CONTEXT, "node_cache", _mock_nc, raising=False)
    monkeypatch.setattr(CONTEXT, "provider_cache", MagicMock(), raising=False)
    monkeypatch.setattr(CONTEXT, "active_tasks", {}, raising=False)
    # metadata_indexer defaults to None (S6 disabled); override per-test when needed.
    monkeypatch.setattr(CONTEXT, "metadata_indexer", None, raising=False)
    # Bypass the live-registry config validator so create_collection tests don't fail
    # due to the mock registry returning an empty stages list.
    monkeypatch.setattr(ConfigValidator, "validate", lambda *a, **kw: [], raising=True)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """
    Async HTTP client targeting the test FastAPI app via in-process ASGI transport.

    No real network socket is opened — requests are dispatched directly to the app.
    """
    transport = httpx.ASGITransport(app=_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─── Auth-specific fixtures ──────────────────────────────────────────────────


@pytest.fixture
def mock_user_repo() -> MagicMock:
    """Mock UserRepository with all auth-layer async methods."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_username = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.list_users = AsyncMock(return_value=[])
    repo.set_active = AsyncMock(return_value=None)
    repo.update_password = AsyncMock(return_value=None)
    repo.upsert_root = AsyncMock()
    return repo


@pytest.fixture
def mock_api_key_repo() -> MagicMock:
    """Mock ApiKeyRepository with all auth-layer async methods."""
    repo = MagicMock()
    repo.get_by_hash = AsyncMock(return_value=None)
    repo.touch_last_used = AsyncMock()
    repo.create = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    repo.revoke = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def mock_grant_repo() -> MagicMock:
    """Mock CollectionGrantRepository with all auth-layer async methods."""
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.list_collection_ids_for_user = AsyncMock(return_value=[])
    repo.list_for_collection = AsyncMock(return_value=[])
    repo.upsert = AsyncMock()
    repo.delete = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """
    Mock AuthService.

    ``effective_collection_role`` defaults to ``GrantRole.ADMIN`` so that existing
    collection-scoped routes pass their auth gate when AUTH_ENABLED=False injects the
    synthetic root principal (root is implicitly admin everywhere in the real service too).

    Tests that need auth-on behaviour override ``resolve_principal``,
    ``effective_collection_role``, or ``CONTEXT.RUNTIME_CONFIG.AUTH_ENABLED`` per test.
    """
    from common_libs.storage.postgres.models import GrantRole

    svc = MagicMock()
    svc.resolve_principal = AsyncMock(return_value=None)
    svc.authenticate = AsyncMock(return_value=None)
    # Default: admin everywhere — mirrors AuthService.effective_collection_role for a root principal.
    svc.effective_collection_role = AsyncMock(return_value=GrantRole.ADMIN)
    svc.generate_api_key = MagicMock(return_value=("plaintext-key", "hash123", "plaintex"))
    svc.mint_token = MagicMock(return_value="minted-jwt-token")
    return svc


# ─── Sample entity factories ──────────────────────────────────────────────────

def make_collection_orm(**overrides: object) -> MagicMock:
    """
    Return a mock ORM collection object that can be passed to model_validate().

    Includes all attributes consumed by ConfigDocument.from_collection() and
    AdmissionValidator so config-endpoint and ingest tests don't need extra setup.
    """
    import datetime
    col = MagicMock()
    col.id = overrides.get("id", uuid.uuid4())
    col.name = overrides.get("name", "Test Collection")
    col.pipeline_version = overrides.get("pipeline_version", "v1")
    col.needs_reindex = overrides.get("needs_reindex", False)
    col.supported_formats = overrides.get("supported_formats", ["pdf"])
    col.max_file_size_bytes = overrides.get("max_file_size_bytes", 10_000_000)
    col.locality_policy = overrides.get("locality_policy", "external_allowed")
    col.embedding_model = overrides.get("embedding_model", "BAAI/bge-m3")
    col.unknown_field_policy = overrides.get("unknown_field_policy", "ignore")
    col.pipeline = overrides.get("pipeline", {})
    col.metadata_fields = overrides.get("metadata_fields", [])
    col.created_at = overrides.get("created_at", datetime.datetime.utcnow())
    # Per-collection resource limit (Brique D) — default to None (no cap) so a bare MagicMock
    # attribute never leaks into the limits response and breaks Pydantic validation.
    col.max_in_flight = overrides.get("max_in_flight", None)
    return col


def make_document_orm(**overrides: object) -> MagicMock:
    """Return a mock ORM document object."""
    import datetime
    doc = MagicMock()
    doc.id = overrides.get("id", uuid.uuid4())
    doc.collection_id = overrides.get("collection_id", uuid.uuid4())
    doc.source_hash = overrides.get("source_hash", "abc123")
    doc.filename = overrides.get("filename", "report.pdf")
    doc.format = overrides.get("format", "pdf")
    doc.language = overrides.get("language", None)
    doc.page_count = overrides.get("page_count", None)
    doc.file_size = overrides.get("file_size", 1024)
    doc.status = overrides.get("status", "done")
    doc.pipeline_version = overrides.get("pipeline_version", "v1")
    doc.user_meta = overrides.get("user_meta", {})
    doc.implicit_meta = overrides.get("implicit_meta", {})
    doc.created_at = overrides.get("created_at", datetime.datetime.utcnow())
    return doc


def make_chunk_row(**overrides: object) -> dict:
    """Return a mock chunk dict as returned by ChunkRepository.get_by_id()."""
    return {
        "id": str(overrides.get("id", uuid.uuid4())),
        "document_id": str(overrides.get("document_id", uuid.uuid4())),
        "config_hash": overrides.get("config_hash", "cfg123"),
        "block_ids": overrides.get("block_ids", ["blk1"]),
        "raw_text": overrides.get("raw_text", "Sample chunk text."),
        "embed_text": overrides.get("embed_text", "Title\nSample chunk text."),
        "token_count": overrides.get("token_count", 10),
        "strategy": overrides.get("strategy", "recursive_structure_aware"),
        "prov": overrides.get("prov", {"pages": [1]}),
    }
