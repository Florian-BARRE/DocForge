# ====== Code Summary ======
# Application entry point — wires services into CONTEXT and creates the FastAPI app.
# RUNTIME_CONFIG must be imported first to register sys.path before any internal imports.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend import CONTEXT, create_app
from backend.libs.health import CollectionHealthService
from backend.libs.search import SearchService
from backend.utils.queue import QueueClient
from config import RUNTIME_CONFIG  # MUST be first — registers backend/libs/ on sys.path
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.edit import GraphEditor
from shared_libs.pipelines.ingest.stages import StageCompiler
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.qdrant import QdrantClient
from shared_libs.services.db.s3 import S3Client


def _build_app() -> FastAPI:
    # 0. Fail a misconfigured boot LOUDLY before wiring anything (e.g. AUTH_ENABLED with no root
    #    token → unrecoverable lockout; wildcard CORS under auth → loud warning).
    RUNTIME_CONFIG.validate()

    # 1. Inject logger and runtime config into the shared context.
    CONTEXT.logger = loggerplusplus.bind(identifier="BACKEND")
    CONTEXT.RUNTIME_CONFIG = RUNTIME_CONFIG

    # 2. Pipeline design services (stateless — one instance for the app's lifetime).
    CONTEXT.pipeline_builder = PipelineBuilder()
    CONTEXT.graph_validator = GraphValidator()
    CONTEXT.graph_editor = GraphEditor()
    CONTEXT.stage_compiler = StageCompiler()

    # 3. Stores + queue — both connect LAZILY (first session / first enqueue), so the app
    # still boots and serves its design surface with no store running.
    CONTEXT.database = Database(
        postgres=PostgresClient(RUNTIME_CONFIG.POSTGRES_DSN),
        qdrant=QdrantClient(RUNTIME_CONFIG.QDRANT_URL, api_key=RUNTIME_CONFIG.QDRANT_API_KEY),
        s3=S3Client(
            endpoint_url=RUNTIME_CONFIG.S3_ENDPOINT_URL,
            access_key=RUNTIME_CONFIG.S3_ACCESS_KEY,
            secret_key=RUNTIME_CONFIG.S3_SECRET_KEY,
            bucket=RUNTIME_CONFIG.S3_BUCKET,
            region=RUNTIME_CONFIG.S3_REGION,
        ),
    )
    CONTEXT.queue = QueueClient(RUNTIME_CONFIG.REDIS_URL)

    # 3b. Search execution — the graph-based search pipeline runs inline (not the arq worker). The
    # runner is stateless; the read port is constructed per-request from the database facade.
    CONTEXT.search_service = SearchService(
        CONTEXT.database, timeout_seconds=RUNTIME_CONFIG.SEARCH_RUN_TIMEOUT_SECONDS
    )

    # 3c. Collection health — on-demand, zero-spend build + reachability probe (no job, no write).
    #     Reuses the shared builder/validator so "does it build?" is answered exactly as a real run.
    CONTEXT.health_service = CollectionHealthService(
        CONTEXT.database, CONTEXT.pipeline_builder, CONTEXT.graph_validator
    )

    # 3. Create the FastAPI application with all routers registered.
    fastapi_app = create_app(
        app_name=RUNTIME_CONFIG.FASTAPI_APP_NAME,
        debug=RUNTIME_CONFIG.FASTAPI_DEBUG_MODE,
        version=RUNTIME_CONFIG.FASTAPI_APP_VERSION,
        description="DocForge — the pipeline design surface API.",
    )

    # 4. Mount the compiled React frontend as static files at the root URL.
    # In dev mode, Vite serves the frontend separately — skip mounting if dist/ doesn't exist.
    if RUNTIME_CONFIG.PATH_ROOT_DIR_APP_FRONTEND.exists():
        fastapi_app.mount(
            "/",
            StaticFiles(directory=RUNTIME_CONFIG.PATH_ROOT_DIR_APP_FRONTEND, html=True),
            name="static",
        )

    # 5. CORS — origins from config (comma-separated; '*' allowed for local dev).
    origins = [
        o.strip() for o in RUNTIME_CONFIG.FASTAPI_CORS_ALLOWED_ORIGINS.split(",") if o.strip()
    ]
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
