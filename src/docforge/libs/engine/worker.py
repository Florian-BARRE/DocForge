# ====== Code Summary ======
# arq WorkerSettings for the DocForge P2/P3/P4 pipeline worker.
# Defines startup/shutdown hooks that build all infrastructure (Postgres, S3, Qdrant, engine,
# classifier, OCR/VLM chains) separately from the FastAPI application context.
# The S2/S4/S5 stages are built via ProviderRegistry from a default PipelineConfig.
# The S6 embed provider is NOT built at startup — it is resolved per-job by StageEngine
# from the collection's embed config ("tei", "openai_compat", or "openai"), see engine._build_s6_from_config.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from arq.connections import RedisSettings
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG  # MUST be first — registers sys.path

# ====== Internal Project Imports ======
from libs.engine.engine import StageEngine
from libs.engine.node_cache import NodeCache
from libs.engine.pipeline_config import build_default_pipeline
from libs.engine.provider_cache import ProviderCallCache
from libs.engine.stages.s0_ingest import S0IngestStage
from libs.engine.stages.s1_parse import S1ParseStage
from libs.engine.stages.s6_embed_index import S6EmbedIndexStage
from libs.engine.tasks import run_pipeline_task
from libs.capabilities.converter import GotenbergConverter
from libs.capabilities.parser import DoclingBackend
from libs.capabilities.registry import ProviderRegistry
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.postgres.repositories import (
    BlockRepository,
    ChunkRepository,
    CollectionRepository,
    DocumentRepository,
    JobRepository,
)
from libs.data.storage.qdrant.client import QdrantStorageClient
from libs.data.storage.s3.client import S3Client

_logger = loggerplusplus.bind(identifier="ARQ_WORKER")


async def startup(ctx: dict) -> None:
    """
    arq worker startup hook — build all infrastructure needed by pipeline tasks.

    This runs once when the worker process starts.  All connections are stored in
    ``ctx`` and reused across task executions.

    Args:
        ctx (dict): arq context dictionary — populated here, consumed in task functions.
    """
    _logger.info(f"Worker starting up…")

    # 1. Connect to PostgreSQL
    postgres = PostgresClient(
        url=PostgresClient.build_url(
            user=RUNTIME_CONFIG.POSTGRES_USER,
            password=RUNTIME_CONFIG.POSTGRES_PASSWORD,
            host=RUNTIME_CONFIG.POSTGRES_HOST,
            port=RUNTIME_CONFIG.POSTGRES_PORT,
            db=RUNTIME_CONFIG.POSTGRES_DB,
        ),
        echo=False,
    )
    await postgres.connect()
    _logger.info(f"Worker: PostgreSQL connected.")

    # 2. Connect to SeaweedFS S3
    s3 = S3Client(
        endpoint_url=RUNTIME_CONFIG.S3_ENDPOINT_URL,
        access_key=RUNTIME_CONFIG.S3_ACCESS_KEY,
        secret_key=RUNTIME_CONFIG.S3_SECRET_KEY,
        bucket=RUNTIME_CONFIG.S3_BUCKET,
        region=RUNTIME_CONFIG.S3_REGION,
    )
    await s3.connect()
    _logger.info(f"Worker: SeaweedFS S3 connected.")

    # 3. Instantiate core providers (S0/S1)
    converter = GotenbergConverter(
        base_url=RUNTIME_CONFIG.GOTENBERG_URL,
        timeout_s=RUNTIME_CONFIG.GOTENBERG_TIMEOUT_S,
    )
    parser = DoclingBackend(use_gpu=RUNTIME_CONFIG.DOCLING_USE_GPU)

    # 4. Instantiate repositories and caches
    document_repo = DocumentRepository()
    block_repo = BlockRepository()
    chunk_repo = ChunkRepository()
    job_repo = JobRepository()
    node_cache = NodeCache()
    provider_cache = ProviderCallCache(postgres=postgres, s3=s3)

    # 5. Provider registry — resolves per-collection PipelineConfig into concrete stages.
    # Full ingestion passes the frozen collection.pipeline so the worker runs the exact
    # stack the playground previewed (parity).  Shares S3 + provider cache with defaults.
    registry = ProviderRegistry(
        s3=s3,
        provider_cache=provider_cache,
        runtime_config=RUNTIME_CONFIG,
    )

    # 6. Build parse chain + S2/S4/S5 stages from the default PipelineConfig
    default_pipeline = build_default_pipeline(RUNTIME_CONFIG)
    default_parse_chain = registry._build_parser_chain(
        default_pipeline.parse.chain, default_pipeline.parse.gate,
    )
    s2_stage, s4_stage, s5_stage = registry.build_enrich_and_chunk_stages(default_pipeline)
    _logger.info(
        f"Worker: S1/S2/S4/S5 ready via registry "
        f"(parse_chain={default_parse_chain.signature()}, "
        f"classifier_chain=len{len(default_pipeline.enrich.classifier_chain)}, "
        f"ocr_chain=len{len(default_pipeline.enrich.ocr_chain)}, "
        f"vlm_chain=len{len(default_pipeline.enrich.vlm_chain)}, "
        f"split={default_pipeline.chunk.split_method.id})"
    )

    # 7. Connect to Qdrant (vector store infrastructure).
    # The actual S6 embed chain is built per-job from the collection's embed config
    # (see StageEngine._build_s6_from_config) — providers in the chain may be
    # TeiEmbedProvider or OpenAIEmbedProvider depending on collection.pipeline.embed.chain.
    # The Qdrant client is shared across all jobs; the embed provider is job-scoped.
    qdrant: QdrantStorageClient | None = None
    s6_stage: S6EmbedIndexStage | None = None
    try:
        qdrant = QdrantStorageClient(
            host=RUNTIME_CONFIG.QDRANT_HOST,
            port=RUNTIME_CONFIG.QDRANT_PORT,
            api_key=RUNTIME_CONFIG.QDRANT_API_KEY or None,
            https=RUNTIME_CONFIG.QDRANT_HTTPS,
        )
        await qdrant.connect()
        _logger.info(
            f"Worker: Qdrant connected "
            f"({RUNTIME_CONFIG.QDRANT_HOST}:{RUNTIME_CONFIG.QDRANT_PORT}) — "
            f"embed provider resolved per-job from collection config"
        )
    except Exception as exc:
        _logger.warning(
            f"Worker: Qdrant not reachable at startup ({exc}). "
            f"Jobs with collection_id will fail loudly — no silent fallback."
        )

    # 8. Assemble the stage engine
    engine = StageEngine(
        s0=S0IngestStage(s3=s3, converter=converter),
        s1=S1ParseStage(parse_chain=default_parse_chain, s3=s3),
        s3=s3,
        postgres=postgres,
        node_cache=node_cache,
        provider_cache=provider_cache,
        document_repo=document_repo,
        block_repo=block_repo,
        chunk_repo=chunk_repo,
        s2=s2_stage,
        s4=s4_stage,
        s5=s5_stage,
        s6=s6_stage,
        registry=registry,
        qdrant=qdrant,
    )

    # 9. Store everything in the arq context
    ctx["postgres"] = postgres
    ctx["s3"] = s3
    ctx["qdrant"] = qdrant
    ctx["engine"] = engine
    ctx["job_repo"] = job_repo
    ctx["collection_repo"] = CollectionRepository()
    ctx["document_repo"] = document_repo

    _logger.info(f"Worker startup complete.")


async def shutdown(ctx: dict) -> None:
    """
    arq worker shutdown hook — close all infrastructure connections cleanly.

    Connections are closed in reverse startup order to respect dependency ordering:
    Qdrant → S3 → Postgres.

    Args:
        ctx (dict): arq context dictionary populated during startup.
    """
    _logger.info(f"Worker shutting down…")

    # 1. Close Qdrant connection (S6 vector store — opened last, closed first)
    if "qdrant" in ctx and ctx["qdrant"] is not None:
        await ctx["qdrant"].close()

    # 2. Close SeaweedFS S3 connection
    if "s3" in ctx:
        await ctx["s3"].close()

    # 3. Close PostgreSQL connection pool
    if "postgres" in ctx:
        await ctx["postgres"].close()

    _logger.info(f"Worker shutdown complete.")


class WorkerSettings:
    """
    arq WorkerSettings class — defines the worker's task list and Redis connection.

    The worker is started with:
        arq libs.pipeline.worker.WorkerSettings
    from within the docforge application directory (/app/docforge in Docker).
    """

    # Tasks available to this worker
    functions = [run_pipeline_task]

    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Redis connection (reads from RUNTIME_CONFIG — config is imported at module top)
    redis_settings = RedisSettings.from_dsn(RUNTIME_CONFIG.REDIS_URL)

    # Retry policy: 3 attempts before marking as permanently failed
    max_tries = 3

    # Health-check interval in seconds
    health_check_interval = 30
