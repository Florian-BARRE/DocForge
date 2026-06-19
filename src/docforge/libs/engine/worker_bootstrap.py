# ====== Code Summary ======
# WorkerBootstrap — builds every infrastructure dependency the arq pipeline worker needs
# (Postgres, SeaweedFS, repositories, caches, provider registry, default stages, Qdrant, and
# the assembled StageEngine) and stores them in the arq context.  Extracted from worker.py so
# the WorkerSettings module stays a thin arq wiring file.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from libs.capabilities.converter import GotenbergConverter
from libs.core.contracts.pipeline_config import build_default_pipeline
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
from libs.engine.assembly import ProviderRegistry
from libs.engine.engine import StageEngine
from libs.engine.node_cache import NodeCache
from libs.engine.provider_cache import ProviderCallCache
from libs.engine.stages.s0_ingest import S0IngestStage
from libs.engine.stages.s1_parse import S1ParseStage
from libs.engine.stages.s6_embed_index import S6EmbedIndexStage

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

        # 3. Instantiate core providers (S0/S1) + repositories + caches
        converter = GotenbergConverter(
            base_url=RUNTIME_CONFIG.GOTENBERG_URL,
            timeout_s=RUNTIME_CONFIG.GOTENBERG_TIMEOUT_S,
        )
        document_repo = DocumentRepository()
        block_repo = BlockRepository()
        chunk_repo = ChunkRepository()
        node_cache = NodeCache()
        provider_cache = ProviderCallCache(postgres=postgres, s3=s3)

        # 4. Provider registry — resolves per-collection PipelineConfig into concrete stages.
        registry = ProviderRegistry(
            s3=s3, provider_cache=provider_cache, runtime_config=RUNTIME_CONFIG,
        )

        # 5. Build parse chain + S2/S4/S5 stages from the default PipelineConfig
        default_pipeline = build_default_pipeline(RUNTIME_CONFIG)
        default_parse_chain = registry._build_parser_chain(
            default_pipeline.parse.chain, default_pipeline.parse.gate,
        )
        s2_stage, s4_stage, s5_stage = registry.build_enrich_and_chunk_stages(default_pipeline)
        _logger.info(
            f"Worker: S1/S2/S4/S5 ready via registry "
            f"(parse_chain={default_parse_chain.signature()}, "
            f"split={default_pipeline.chunk.split_method.id})"
        )

        # 6. Connect to Qdrant; the S6 embed chain is built per-job from the collection config.
        qdrant = await cls._connect_qdrant()
        s6_stage: S6EmbedIndexStage | None = None

        # 7. Assemble the stage engine
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

        # 8. Store everything in the arq context
        ctx["postgres"] = postgres
        ctx["s3"] = s3
        ctx["qdrant"] = qdrant
        ctx["engine"] = engine
        ctx["job_repo"] = JobRepository()
        ctx["collection_repo"] = CollectionRepository()
        ctx["document_repo"] = document_repo

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
