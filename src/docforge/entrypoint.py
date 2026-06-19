# ====== Code Summary ======
# Application entry point — wires all services into CONTEXT and creates the FastAPI app.
# uvicorn targets this module: uvicorn docforge.entrypoint:app  (from WORKDIR /app)
# OR: uvicorn entrypoint:app  (from WORKDIR /app/docforge)

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG  # MUST be first — registers sys.path + configures logging

from backend import CONTEXT, create_app
from libs.core.metadata.indexer import MetadataIndexer
from libs.engine.engine import StageEngine
from libs.data.retrieval.hybrid_search import HybridSearchService
from libs.engine.node_cache import NodeCache
from libs.engine.provider_cache import ProviderCallCache
from libs.engine.stages.s0_ingest import S0IngestStage
from libs.engine.stages.s1_parse import S1ParseStage
from libs.engine.stages.s2_enrich import S2EnrichStage
from libs.engine.stages.chunking import TokenBudgetSplitter
from libs.engine.stages.s4_chunk import S4ChunkStage
from libs.engine.stages.s5_contextualize import S5ContextualizeStage
from libs.capabilities.converter import GotenbergConverter
from libs.capabilities.device_manager import DeviceManager
from libs.capabilities.embed.local.tei import TeiEmbedProvider
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
from libs.data.storage.qdrant.client import QdrantStorageClient
from libs.data.storage.s3.client import S3Client


def _build_app() -> FastAPI:
    """
    Assemble and return a fully configured FastAPI application.

    Steps:
    1. Bind logger and inject RUNTIME_CONFIG into CONTEXT.
    2. Instantiate storage clients (Postgres, S3).
    3. Instantiate all repositories (collections, documents, blocks, jobs).
    4. Instantiate device manager and ML providers (Gotenberg, Docling).
    5. Instantiate P2 pipeline infrastructure (NodeCache, ProviderCallCache).
    6. Build S2/S4/S5 stages from default PipelineConfig (derived from RUNTIME_CONFIG env vars).
    7. Build S6 embedding + indexing stack — attempted always; falls back to None if
       TEI/Qdrant is unreachable (infrastructure availability, not a toggle).
    8. Assemble StageEngine + ProviderRegistry and inject into CONTEXT.
    9. Create and return the FastAPI app (lifespan connects storage + arq pool).

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

    # 4. Instantiate device manager (GPU/CPU detection deferred to lifespan)
    CONTEXT.device_manager = DeviceManager()

    # 5. Instantiate ML providers
    CONTEXT.converter = GotenbergConverter(
        base_url=RUNTIME_CONFIG.GOTENBERG_URL,
        timeout_s=RUNTIME_CONFIG.GOTENBERG_TIMEOUT_S,
    )
    # use_gpu configured via env; DeviceManager.detect() runs in lifespan
    # Kept on CONTEXT for backward compatibility — the chain owns the live instance.
    CONTEXT.parser = DoclingBackend(use_gpu=RUNTIME_CONFIG.DOCLING_USE_GPU)

    # 6. Instantiate P2 pipeline infrastructure
    CONTEXT.node_cache = NodeCache()
    CONTEXT.provider_cache = ProviderCallCache(postgres=CONTEXT.postgres, s3=CONTEXT.s3)

    # 7. Provider registry — resolves a per-run PipelineConfig into concrete stages.
    # This is what lets the playground (dry_run) and per-collection pipelines tune the
    # exact same engine.  Shares S3 + provider cache with the env-built default stages.
    CONTEXT.registry = ProviderRegistry(
        s3=CONTEXT.s3,
        provider_cache=CONTEXT.provider_cache,
        runtime_config=RUNTIME_CONFIG,
    )

    # Build the parse chain + S2/S4/S5 stages from the deployment defaults.
    from libs.engine.pipeline_config import build_default_pipeline
    default_pipeline = build_default_pipeline(RUNTIME_CONFIG)
    default_parse_chain = CONTEXT.registry._build_parser_chain(
        default_pipeline.parse.chain, default_pipeline.parse.gate,
    )
    s2_stage, s4_stage, s5_stage = CONTEXT.registry.build_enrich_and_chunk_stages(default_pipeline)

    # 8. Qdrant client + query-time embed provider (TEI, configured via RUNTIME_CONFIG).
    # The query-time provider (HybridSearchService, MetadataIndexer) uses the TEI server
    # declared in env vars — separate from the per-collection ingestion embed provider.
    # S6 ingestion providers are resolved per-job by StageEngine._build_s6_from_config
    # from the collection's embed config (tei_bge_m3 or openai_compat) — not built here.
    CONTEXT.qdrant = QdrantStorageClient(
        host=RUNTIME_CONFIG.QDRANT_HOST,
        port=RUNTIME_CONFIG.QDRANT_PORT,
        api_key=RUNTIME_CONFIG.QDRANT_API_KEY or None,
        https=RUNTIME_CONFIG.QDRANT_HTTPS,
    )
    _query_embed = TeiEmbedProvider(
        base_url=RUNTIME_CONFIG.TEI_BASE_URL,
        batch_size=RUNTIME_CONFIG.TEI_BATCH_SIZE,
    )
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

    CONTEXT.stage_engine = StageEngine(
        s0=S0IngestStage(s3=CONTEXT.s3, converter=CONTEXT.converter),
        s1=S1ParseStage(parse_chain=default_parse_chain, s3=CONTEXT.s3),
        s3=CONTEXT.s3,
        postgres=CONTEXT.postgres,
        node_cache=CONTEXT.node_cache,
        provider_cache=CONTEXT.provider_cache,
        document_repo=CONTEXT.document_repo,
        block_repo=CONTEXT.block_repo,
        chunk_repo=CONTEXT.chunk_repo,
        s2=s2_stage,
        s4=s4_stage,
        s5=s5_stage,
        s6=None,  # built per-job from collection embed config by _build_s6_from_config
        registry=CONTEXT.registry,
        qdrant=CONTEXT.qdrant,
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
    frontend_dist = RUNTIME_CONFIG.PATH_ROOT_DIR_FRONTEND
    if frontend_dist.exists():
        fastapi_app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="static",
        )

    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
