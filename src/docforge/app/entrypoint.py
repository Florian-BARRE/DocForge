# ====== Code Summary ======
# Application entry point — wires all services into CONTEXT and creates the FastAPI app.
# uvicorn targets this module from WORKDIR /app/backend:  uvicorn entrypoint:app

# ====== Path bootstrap (multi-root layout) ======
# This app lives in src/backend/; shared code lives in src/common/. Register both on
# sys.path BEFORE any internal import so that:
#   - src/common  resolves `config` and `common_libs.*`  (shared)
#   - src/backend resolves `backend`, `entrypoint`, and `libs.*`  (backend-dedicated)
import pathlib as _pathlib
import sys as _sys

_BACKEND_DIR = _pathlib.Path(__file__).resolve().parent
_COMMON_DIR = _BACKEND_DIR.parent / "common"
for _p in (_COMMON_DIR, _BACKEND_DIR):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG  # registers the shared common/ tree on sys.path + logging

from backend import CONTEXT, create_app
from backend.libs.admission import ResourceAdmitter
from backend.libs.auth import AuthService
from backend.libs.search.metadata_indexer.indexer import MetadataIndexer
from backend.libs.search.hybrid.service import HybridSearchService
from common_libs.pipeline.caches.node_cache import NodeCache
from common_libs.pipeline.caches.provider_cache import ProviderCallCache
from common_libs.pipeline.bricks.providers.converter import GotenbergConverter
from common_libs.pipeline.bricks.providers.device import DeviceManager
from common_libs.providers.embed import BgeServerEmbedConfig
from common_libs.pipeline.assembly import ProviderRegistry
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.repositories import (
    ApiKeyRepository,
    BlockRepository,
    ChunkRepository,
    CollectionRepository,
    ConfigRepository,
    DocumentRepository,
    JobRepository,
    UserRepository,
)
from common_libs.storage.qdrant.client import QdrantStorageClient
from common_libs.storage.s3.client import S3Client


def _build_app() -> FastAPI:
    """
    Assemble and return a fully configured FastAPI application.

    Steps:
    1. Bind logger and inject RUNTIME_CONFIG into CONTEXT.
    2. Instantiate storage clients (Postgres, S3).
    3. Instantiate all repositories (collections, documents, blocks, jobs).
    4. Instantiate the device manager, Gotenberg converter, and resource-admission gate.
    5. Instantiate pipeline caches (NodeCache, ProviderCallCache) and the provider registry.
    6. Build the query-time search stack — Qdrant client, TEI embed provider,
       HybridSearchService and MetadataIndexer (None when TEI/Qdrant is unreachable).
    7. Create and return the FastAPI app (lifespan connects storage + arq pool).

    Note:
        The backend never runs the ingestion pipeline (S0 → S6) — that is the arq
        worker's job (see libs/pipeline/worker/worker_bootstrap.py).  The backend only
        needs the query-time search stack, storage, and the registry for config
        validation and schema discovery.

    Returns:
        FastAPI: The configured application instance, ready for uvicorn.
    """
    # 1. Bind structured logger and config to CONTEXT
    CONTEXT.logger = loggerplusplus.bind(identifier="DOCFORGE")
    CONTEXT.RUNTIME_CONFIG = RUNTIME_CONFIG

    # 2. Instantiate storage clients (connections are made in lifespan)
    CONTEXT.postgres = PostgresClient(
        url=PostgresClient.build_url(
            user=RUNTIME_CONFIG.POSTGRES_USER,
            password=RUNTIME_CONFIG.POSTGRES_PASSWORD,
            host=RUNTIME_CONFIG.POSTGRES_HOST,
            port=RUNTIME_CONFIG.POSTGRES_PORT,
            db=RUNTIME_CONFIG.POSTGRES_DB,
        ),
        echo=RUNTIME_CONFIG.FASTAPI_DEBUG_MODE,
    )

    CONTEXT.s3 = S3Client(
        endpoint_url=RUNTIME_CONFIG.S3_ENDPOINT_URL,
        access_key=RUNTIME_CONFIG.S3_ACCESS_KEY,
        secret_key=RUNTIME_CONFIG.S3_SECRET_KEY,
        bucket=RUNTIME_CONFIG.S3_BUCKET,
        region=RUNTIME_CONFIG.S3_REGION,
        public_url=RUNTIME_CONFIG.S3_PUBLIC_URL or None,
    )

    # 3. Instantiate database repositories
    CONTEXT.collection_repo = CollectionRepository()
    CONTEXT.config_repo = ConfigRepository()
    CONTEXT.document_repo = DocumentRepository()
    CONTEXT.block_repo = BlockRepository()
    CONTEXT.chunk_repo = ChunkRepository()
    CONTEXT.job_repo = JobRepository()

    # 3b. Auth repositories + service (authentication + per-collection authorization). The service
    # opens its own sessions via the Postgres client and resolves credentials (root key | JWT | DB
    # API key). The root account is bootstrapped in lifespan once the DB connection is live.
    CONTEXT.user_repo = UserRepository()
    CONTEXT.api_key_repo = ApiKeyRepository()
    CONTEXT.auth_service = AuthService(
        postgres=CONTEXT.postgres,
        user_repo=CONTEXT.user_repo,
        api_key_repo=CONTEXT.api_key_repo,
        root_api_key=RUNTIME_CONFIG.AUTH_ROOT_API_KEY,
        jwt_secret=RUNTIME_CONFIG.AUTH_JWT_SECRET,
        jwt_ttl_minutes=RUNTIME_CONFIG.AUTH_JWT_TTL_MINUTES,
        root_username=RUNTIME_CONFIG.AUTH_ROOT_USERNAME,
        root_password=RUNTIME_CONFIG.AUTH_ROOT_PASSWORD,
    )

    # 4. Instantiate device manager (GPU/CPU detection deferred to lifespan)
    CONTEXT.device_manager = DeviceManager()

    # 4b. Resource-admission gate (Brique D). Needs only the global limits at construction; the live
    # collaborators (queue_introspector / job_repo) are passed per-call from the ingest router, so it
    # is built here like device_manager rather than in lifespan.
    CONTEXT.resource_admitter = ResourceAdmitter(
        enabled=RUNTIME_CONFIG.ADMISSION_ENABLED,
        max_queue_depth=RUNTIME_CONFIG.ADMISSION_MAX_QUEUE_DEPTH,
        max_in_flight_global=RUNTIME_CONFIG.ADMISSION_MAX_IN_FLIGHT_GLOBAL,
    )

    # 5. Instantiate the document converter (Gotenberg). DeviceManager.detect() runs in lifespan.
    CONTEXT.converter = GotenbergConverter(
        base_url=RUNTIME_CONFIG.GOTENBERG_URL,
        timeout_s=RUNTIME_CONFIG.GOTENBERG_TIMEOUT_S,
    )

    # 6. Instantiate P2 pipeline infrastructure
    CONTEXT.node_cache = NodeCache()
    CONTEXT.provider_cache = ProviderCallCache(postgres=CONTEXT.postgres, s3=CONTEXT.s3)

    # 7. Provider registry — resolves a per-run PipelineConfig into concrete stages.
    # Used by the search router (per-collection search pipelines) and by config
    # validation / schema discovery (describe_stages).  The ingestion stages are built
    # by the arq worker, not here — the backend never runs the ingestion pipeline.
    CONTEXT.registry = ProviderRegistry(
        s3=CONTEXT.s3,
        provider_cache=CONTEXT.provider_cache,
        runtime_config=RUNTIME_CONFIG,
    )

    # 8. Qdrant client + shared query-time embed provider.
    # The query-time provider feeds HybridSearchService + MetadataIndexer. It is built from the
    # bge_server provider's STRUCTURAL default (local bge model host) — NOT from any env var:
    # provider URLs/secrets are per-collection now. Per-collection SEARCH still builds its own
    # embed provider from the queried collection's config (build_search_pipeline). S6 ingestion
    # providers are resolved per-job by the worker from the collection's embed config.
    CONTEXT.qdrant = QdrantStorageClient(
        host=RUNTIME_CONFIG.QDRANT_HOST,
        port=RUNTIME_CONFIG.QDRANT_PORT,
        api_key=RUNTIME_CONFIG.QDRANT_API_KEY or None,
        https=RUNTIME_CONFIG.QDRANT_HTTPS,
    )
    # Dense-only here so the shared query/metadata embed stays compatible with dense-indexed
    # collections; a collection opts into sparse via its own pipeline (resolved per search).
    _query_embed = BgeServerEmbedConfig(embed_sparse=False).build()
    CONTEXT.retrieval = HybridSearchService(
        embed_provider=_query_embed,
        qdrant=CONTEXT.qdrant,
        chunk_repo=CONTEXT.chunk_repo,
    )
    CONTEXT.metadata_indexer = MetadataIndexer(
        embed_provider=_query_embed,
        qdrant=CONTEXT.qdrant,
        chunk_repo=CONTEXT.chunk_repo,
    )

    # 9. Create FastAPI app (lifespan connects storage + arq pool)
    fastapi_app = create_app(
        app_name=RUNTIME_CONFIG.FASTAPI_APP_NAME,
        debug=RUNTIME_CONFIG.FASTAPI_DEBUG_MODE,
        version=RUNTIME_CONFIG.APP_VERSION,
        description="DocForge — Document Intelligence Platform",
    )

    # 10. Mount the compiled React frontend as static files.
    # Only mounted when the dist directory exists (i.e., after `npm run build`).
    # In dev, Vite serves the frontend separately on :5173 with HMR.
    # The frontend lives in the backend tree (src/backend/frontend/dist) — computed
    # relative to this file rather than via the shared RUNTIME_CONFIG.
    frontend_dist = _BACKEND_DIR / "frontend" / "dist"
    if frontend_dist.exists():
        fastapi_app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="static",
        )

    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
