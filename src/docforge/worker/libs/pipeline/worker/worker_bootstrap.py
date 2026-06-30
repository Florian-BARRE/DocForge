# ====== Code Summary ======
# WorkerBootstrap — builds every infrastructure dependency the arq pipeline worker needs
# (Postgres, SeaweedFS, repositories, caches, the Gotenberg converter, the markdown serialiser, Qdrant,
# and the flow IngestRunner) and stores them in the arq context.  Extracted from worker.py so the
# WorkerSettings module stays a thin arq wiring file. Ingestion runs exclusively through the flow
# node-engine (FlowPipelineBuilder + FlowEngine + WorkerEngineHooks); the legacy DynamicStageEngine /
# ProviderRegistry path is gone.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import socket
from uuid import uuid4

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from common_libs.domain.ir.serializer import MarkdownSerializer
from common_libs.observability.events import EventPublisher
from common_libs.observability.heartbeat import HeartbeatWriter
from libs.observability.metrics import MetricsCollector
from common_libs.pipelines.capabilities.caches import NodeCache, ProviderCallCache
from common_libs.providers.converter import GotenbergConverter
from libs.pipeline.run import IngestRunner
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.repositories import (
    BlockRepository,
    ChunkRepository,
    CollectionRepository,
    DocumentRepository,
    JobRepository,
)
from common_libs.storage.qdrant.client import QdrantStorageClient
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from .heartbeat import WorkerHeartbeatLoop

_logger = loggerplusplus.bind(identifier="ARQ_WORKER")


class WorkerBootstrap:
    """
    Static builder for the arq worker's infrastructure context.

    ``build`` instantiates every dependency in dependency order and populates the arq ``ctx``
    dict.  ``teardown`` closes the connections in reverse order.  No instance state.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("WorkerBootstrap is a static-only class and cannot be instantiated.")

    @classmethod
    async def build(cls, ctx: dict) -> None:
        """
        Build all worker infrastructure and store it in the arq context.

        Args:
            ctx (dict): arq context dictionary — populated here, consumed in task functions.
        """
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

        # 3. Repositories + caches + the infra providers the pipeline injects as services.
        document_repo = DocumentRepository()
        block_repo = BlockRepository()
        chunk_repo = ChunkRepository()
        node_cache = NodeCache(postgres=postgres)
        provider_cache = ProviderCallCache(postgres=postgres, s3=s3)
        # Gotenberg (office/HTML -> PDF) + the IR -> markdown serialiser are INFRA: one deployment URL
        # from RUNTIME_CONFIG, built once and injected as pipeline services (never hardcoded/per-call).
        converter = GotenbergConverter(
            base_url=RUNTIME_CONFIG.GOTENBERG_URL, timeout_s=RUNTIME_CONFIG.GOTENBERG_TIMEOUT_S,
        )
        serializer = MarkdownSerializer()

        # 4. Connect to Qdrant; the embed chain is built per-job from the collection config.
        qdrant = await cls._connect_qdrant()

        # 5. Build the flow ingest runner (the sole ingestion path). It rebuilds the per-collection
        # pipeline per job from the stored config; the infra here is long-lived + reused across jobs.
        runner = IngestRunner(
            object_store=s3,
            converter=converter,
            postgres=postgres,
            qdrant=qdrant,
            node_cache=node_cache,
            provider_cache=provider_cache,
            serializer=serializer,
            document_repo=document_repo,
            block_repo=block_repo,
            chunk_repo=chunk_repo,
            defaults_cfg=RUNTIME_CONFIG,
        )
        _logger.info(f"Worker: flow ingest runner ready.")

        # 6. Store everything in the arq context
        ctx["postgres"] = postgres
        ctx["s3"] = s3
        ctx["qdrant"] = qdrant
        ctx["runner"] = runner
        ctx["job_repo"] = JobRepository()
        ctx["collection_repo"] = CollectionRepository()
        ctx["document_repo"] = document_repo

        # 9. Observability — worker identity, event publisher, and heartbeat loop.
        # arq populates ctx["redis"] (the worker's ArqRedis pool) before on_startup runs, so it
        # is reused here for all telemetry. The loop object is built now and started in worker.py.
        redis = ctx["redis"]
        hostname = socket.gethostname()
        pid = os.getpid()
        worker_id = f"{hostname}:{pid}:{uuid4().hex[:8]}"
        ctx["worker_id"] = worker_id
        ctx["current_job_id"] = None          # mutated by run_pipeline_task while a job runs
        ctx["jobs_processed"] = 0             # incremented by run_pipeline_task on completion
        event_publisher = EventPublisher(redis)
        ctx["event_publisher"] = event_publisher
        ctx["heartbeat_loop"] = WorkerHeartbeatLoop(
            writer=HeartbeatWriter(redis, worker_id, RUNTIME_CONFIG.OBS_HEARTBEAT_TTL_S),
            publisher=event_publisher,
            metrics=MetricsCollector(enabled=RUNTIME_CONFIG.OBS_METRICS_ENABLED),
            ctx=ctx,
            worker_id=worker_id,
            hostname=hostname,
            pid=pid,
            interval_s=RUNTIME_CONFIG.OBS_HEARTBEAT_INTERVAL_S,
        )
        _logger.info(f"Worker: observability ready (worker_id={worker_id}).")

    @staticmethod
    async def _connect_qdrant() -> QdrantStorageClient | None:
        """
        Connect to Qdrant, returning None when it is unreachable at startup.

        Jobs with a collection_id then fail loudly — there is no silent fallback.

        Returns:
            QdrantStorageClient | None: Connected client, or None when unreachable.
        """
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
            return qdrant
        except Exception as exc:
            _logger.warning(
                f"Worker: Qdrant not reachable at startup ({exc}). "
                f"Jobs with collection_id will fail loudly — no silent fallback."
            )
            return None

    @staticmethod
    async def teardown(ctx: dict) -> None:
        """
        Close all infrastructure connections in reverse startup order.

        Order: Qdrant → S3 → Postgres.

        Args:
            ctx (dict): arq context dictionary populated during build().
        """
        if "qdrant" in ctx and ctx["qdrant"] is not None:
            await ctx["qdrant"].close()
        if "s3" in ctx:
            await ctx["s3"].close()
        if "postgres" in ctx:
            await ctx["postgres"].close()


# ------------------- Public API ------------------- #
__all__ = ["WorkerBootstrap"]
