# ====== Code Summary ======
# Defines RUNTIME_CONFIG (env-based settings) and configures the loggerplusplus sinks.
# This file is always the first module imported in any entry point.

# ====== Standard Library Imports ======
import os
import pathlib
import sys

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env
from loggerplusplus import formats as lpp_formats
from loggerplusplus import loggerplusplus

# ─── Reset logger before anything else ───
loggerplusplus.remove()

# ─── Optional DEV_MODE early logger ───
# DEV_MODE is read directly from os.environ (not via env()) because it must
# activate a temporary debug sink BEFORE the RUNTIME_CONFIG class is evaluated.
# This sink is removed immediately after and replaced by the real sinks below.
if os.environ.get("DEV_MODE"):
    loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
    _dev_logger = loggerplusplus.bind(identifier="DEV")
    _dev_logger.warning(f"DEV MODE is activated !")
    loggerplusplus.remove()


class RUNTIME_CONFIG(EnvConfigLoader):
    """
    Environment-driven runtime configuration for DocForge.

    All variables are read from environment variables at class evaluation time.
    Secrets (keys, passwords) are automatically masked in ``__str__`` output.
    Import this class before any other internal import in every entry point so that
    ``sys.path.append`` registers ``libs/`` before other modules are resolved.
    """

    # ───── Paths & dirs ─────
    # Root of the docforge application (src/docforge/)
    PATH_ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent

    # Register root dir on sys.path — modules now directly under docforge root.
    # Allows flat imports: from providers import ..., from ir import ..., etc.
    sys.path.append(str(PATH_ROOT_DIR))  # modules now directly under docforge root

    # ───── Logging (ALWAYS present in every project) ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

    # ───── FastAPI ─────
    FASTAPI_APP_NAME: str = env("FASTAPI_APP_NAME", default="DocForge")
    FASTAPI_DEBUG_MODE: bool = env("FASTAPI_DEBUG_MODE", cast=bool, default="false")
    CORS_ALLOWED_ORIGINS: str = env("CORS_ALLOWED_ORIGINS", default="http://localhost:5173")
    # Application version surfaced in OpenAPI docs and the /health/ping endpoint
    APP_VERSION: str = env("APP_VERSION", default="0.1.0")

    # ───── Database (PostgreSQL) ─────
    POSTGRES_USER: str = env("POSTGRES_USER", default="docforge")
    POSTGRES_PASSWORD: str = env("POSTGRES_PASSWORD")
    POSTGRES_HOST: str = env("POSTGRES_HOST", default="localhost")
    POSTGRES_PORT: int = env("POSTGRES_PORT", cast=int, default="5432")
    POSTGRES_DB: str = env("POSTGRES_DB", default="docforge")

    # ───── Object store (SeaweedFS — S3-compatible API, port 8333) ─────
    # SeaweedFS replaces MinIO: open-source, actively maintained, S3-compat.
    # Client code uses aioboto3 with endpoint_url pointing to SeaweedFS S3 port.
    S3_ENDPOINT_URL: str = env("S3_ENDPOINT_URL", default="http://localhost:8333")
    S3_ACCESS_KEY: str = env("S3_ACCESS_KEY", default="seaweedfs_admin")
    S3_SECRET_KEY: str = env("S3_SECRET_KEY")
    S3_BUCKET: str = env("S3_BUCKET", default="docforge-objects")
    S3_REGION: str = env("S3_REGION", default="us-east-1")
    # External-facing S3 URL for presigned URLs — replaces the internal hostname so
    # clients outside the container network can download objects via presigned URLs.
    # Leave empty to use S3_ENDPOINT_URL as-is (internal access only).
    S3_PUBLIC_URL: str = env("S3_PUBLIC_URL", default="", required=False)

    # ───── Gotenberg (document conversion) ─────
    GOTENBERG_URL: str = env("GOTENBERG_URL", default="http://localhost:3000")
    GOTENBERG_TIMEOUT_S: int = env("GOTENBERG_TIMEOUT_S", cast=int, default="120")

    # ───── Pipeline providers ─────
    # Default parser backend (docling | minerU | marker)
    PARSER_DEFAULT_BACKEND: str = env("PARSER_DEFAULT_BACKEND", default="docling")

    # Docling: use GPU acceleration when available
    DOCLING_USE_GPU: bool = env("DOCLING_USE_GPU", cast=bool, default="false")

    # ───── Redis (arq job queue — P2) ─────
    REDIS_URL: str = env("REDIS_URL", default="redis://localhost:6379")

    # ───── Workers & observability (Brique A) ─────
    # Max concurrent pipeline jobs per arq worker process (arq `max_jobs`).
    WORKER_MAX_JOBS: int = env("WORKER_MAX_JOBS", cast=int, default="10")
    # Enable arq job abort (required by POST /jobs/{id}/cancel). Read-only/safe.
    WORKER_ALLOW_ABORT: bool = env("WORKER_ALLOW_ABORT", cast=bool, default="true")
    # Worker heartbeat write cadence (seconds) — how often a worker reports liveness + gauges.
    OBS_HEARTBEAT_INTERVAL_S: int = env("OBS_HEARTBEAT_INTERVAL_S", cast=int, default="5")
    # Heartbeat Redis key TTL (seconds) — ~3x interval so dead workers vanish automatically.
    OBS_HEARTBEAT_TTL_S: int = env("OBS_HEARTBEAT_TTL_S", cast=int, default="15")
    # Gate psutil/pynvml gauge collection (set false to disable resource sampling entirely).
    OBS_METRICS_ENABLED: bool = env("OBS_METRICS_ENABLED", cast=bool, default="true")
    # SSE comment-ping cadence (seconds) — keeps proxies/load-balancers from killing idle streams.
    SSE_KEEPALIVE_SECONDS: int = env("SSE_KEEPALIVE_SECONDS", cast=int, default="15")
    # Per-client SSE fan-out queue size; on overflow the broadcaster drops the oldest event so one
    # slow browser cannot grow memory unboundedly (back-pressure, brique C).
    SSE_CLIENT_QUEUE_MAXSIZE: int = env("SSE_CLIENT_QUEUE_MAXSIZE", cast=int, default="100")

    # ───── Resource admission / back-pressure (Brique D) ─────
    # Master switch for the runtime resource gate (queue depth / in-flight / budget back-pressure).
    ADMISSION_ENABLED: bool = env("ADMISSION_ENABLED", cast=bool, default="true")
    # Reject ingest when the arq backlog (ZCARD) reaches this depth (0 = unlimited).
    ADMISSION_MAX_QUEUE_DEPTH: int = env("ADMISSION_MAX_QUEUE_DEPTH", cast=int, default="0")
    # Reject ingest when running jobs (all collections) reach this count (0 = unlimited).
    ADMISSION_MAX_IN_FLIGHT_GLOBAL: int = env("ADMISSION_MAX_IN_FLIGHT_GLOBAL", cast=int, default="0")

    # ───── P3 — S2 Enrichment (OCR / VLM / classifier) ─────
    # Figure classifier: "layout_labels" (heuristic, no model) or "vit_onnx" (ONNX model)
    CLASSIFIER_TYPE: str = env("CLASSIFIER_TYPE", default="layout_labels")
    # Path to the ONNX model file (only used when CLASSIFIER_TYPE=vit_onnx)
    CLASSIFIER_ONNX_MODEL_PATH: str = env(
        "CLASSIFIER_ONNX_MODEL_PATH", default="models/classifier.onnx"
    )
    # Use GPU for ONNX inference (requires onnxruntime-gpu)
    CLASSIFIER_USE_GPU: bool = env("CLASSIFIER_USE_GPU", cast=bool, default="false")

    # PaddleOCR — local GPU/CPU OCR provider (cost_per_page=0.0)
    OCR_PADDLE_ENABLED: bool = env("OCR_PADDLE_ENABLED", cast=bool, default="false")
    OCR_PADDLE_USE_GPU: bool = env("OCR_PADDLE_USE_GPU", cast=bool, default="false")

    # Mistral OCR — cloud OCR API (escalation fallback for PaddleOCR, confidence=1.0)
    MISTRAL_OCR_ENABLED: bool = env("MISTRAL_OCR_ENABLED", cast=bool, default="false")
    MISTRAL_OCR_API_URL: str = env("MISTRAL_OCR_API_URL", default="https://api.mistral.ai/v1")
    MISTRAL_OCR_API_KEY: str = env("MISTRAL_OCR_API_KEY", default="")
    MISTRAL_OCR_MODEL: str = env("MISTRAL_OCR_MODEL", default="mistral-ocr-latest")
    MISTRAL_OCR_TIMEOUT_S: int = env("MISTRAL_OCR_TIMEOUT_S", cast=int, default="60")

    # VLM (Vision Language Model) — any OpenAI-compatible vision endpoint
    VLM_ENABLED: bool = env("VLM_ENABLED", cast=bool, default="false")
    VLM_API_BASE_URL: str = env("VLM_API_BASE_URL", default="http://localhost:8080/v1")
    VLM_API_KEY: str = env("VLM_API_KEY", default="local")
    VLM_MODEL: str = env("VLM_MODEL", default="Qwen/Qwen2.5-VL-7B-Instruct")
    VLM_TIMEOUT_S: int = env("VLM_TIMEOUT_S", cast=int, default="120")
    VLM_MAX_TOKENS: int = env("VLM_MAX_TOKENS", cast=int, default="512")
    VLM_COST_PER_CALL: float = env("VLM_COST_PER_CALL", cast=float, default="0.0")

    # Confidence threshold for OCR escalation — call next provider if below this value
    OCR_CONFIDENCE_THRESHOLD: float = env("OCR_CONFIDENCE_THRESHOLD", cast=float, default="0.85")

    # Maximum USD budget for OCR/VLM API calls per pipeline run (0.0 = unlimited)
    ENRICH_MAX_BUDGET_USD: float = env("ENRICH_MAX_BUDGET_USD", cast=float, default="0.0")

    # ───── P4 — S4 Chunking ─────
    # Maximum estimated tokens per text chunk (figures and tables are always a single chunk)
    CHUNK_MAX_TOKENS: int = env("CHUNK_MAX_TOKENS", cast=int, default="512")
    # Number of blocks to prepend from the prior chunk for context overlap (0 = disabled)
    CHUNK_OVERLAP_BLOCKS: int = env("CHUNK_OVERLAP_BLOCKS", cast=int, default="0")

    # ───── P4 — S6 Embedding + Indexing ─────
    # BGE-M3 TEI (Text Embeddings Inference) server URL
    TEI_BASE_URL: str = env("TEI_BASE_URL", default="http://localhost:8080")
    # Number of texts sent to TEI per HTTP request
    TEI_BATCH_SIZE: int = env("TEI_BATCH_SIZE", cast=int, default="64")
    # Whether the SHARED query/re-embed TEI provider also requests sparse (BM25) vectors.
    # Set False for a dense-only BGE-M3 deployment (no sparse head) — otherwise /embed_sparse
    # returns HTTP 424 and breaks search-query embedding + chunk/metadata re-embed. Per-INGEST
    # sparse is configured per-collection (pipeline.embed.chain[].embed_sparse); this flag only
    # governs the deployment-wide provider used by HybridSearchService + MetadataIndexer.
    TEI_EMBED_SPARSE: bool = env("TEI_EMBED_SPARSE", cast=bool, default="True")

    # OpenAI / OpenAI-compatible cloud embed provider.
    # Consumed by merge_defaults() on OpenAIEmbedConfig for both ingestion (S6) and
    # query-time embedding (search router) — configure once, used symmetrically.
    # OPENAI_API_KEY takes precedence; EMBED_API_KEY is the generic fallback.
    OPENAI_API_KEY: str = env("OPENAI_API_KEY", required=False, default="")
    EMBED_API_KEY: str = env("EMBED_API_KEY", required=False, default="")

    # Qdrant vector store connection
    QDRANT_HOST: str = env("QDRANT_HOST", default="localhost")
    QDRANT_PORT: int = env("QDRANT_PORT", cast=int, default="6333")
    # API key for Qdrant Cloud (empty string = local unauthenticated)
    QDRANT_API_KEY: str = env("QDRANT_API_KEY", default="")
    # Use HTTPS (set to true for Qdrant Cloud, false for self-hosted)
    QDRANT_HTTPS: bool = env("QDRANT_HTTPS", cast=bool, default="false")

    # ───── Search pipeline — reranker ─────
    # BGE-Reranker-v2-m3 via TEI (separate container from the embed TEI).
    # Consumed by BgeRerankerConfig.merge_defaults() when rerank is enabled.
    BGE_RERANKER_URL: str = env("BGE_RERANKER_URL", required=False, default="http://reranker:80")
    BGE_RERANKER_BATCH_SIZE: int = env("BGE_RERANKER_BATCH_SIZE", cast=int, default="32")
    # Cohere Rerank API key — consumed by CohereRerankConfig.merge_defaults().
    COHERE_API_KEY: str = env("COHERE_API_KEY", required=False, default="")

    # ───── Search pipeline — query transform LLM ─────
    # OpenAI-compatible LLM endpoint for rewrite / HyDE / multi-query strategies.
    # Consumed by LocalLLMConfig.merge_defaults() when a query transform is configured.
    LLM_API_BASE_URL: str = env("LLM_API_BASE_URL", required=False, default="http://localhost:8080/v1")
    LLM_API_KEY: str = env("LLM_API_KEY", required=False, default="local")
    LLM_MODEL: str = env("LLM_MODEL", required=False, default="Qwen/Qwen2.5-7B-Instruct")

    # ───── Derived paths ─────
    PATH_ROOT_DIR_FRONTEND: pathlib.Path = PATH_ROOT_DIR / "frontend" / "dist"


# ─── Apply logging configuration AFTER class definition ───
_lpp_format_cls = getattr(lpp_formats, RUNTIME_CONFIG.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat)
_lpp_format = _lpp_format_cls()

if RUNTIME_CONFIG.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=RUNTIME_CONFIG.LOGGING_CONSOLE_LEVEL,
        format=_lpp_format,
    )

if RUNTIME_CONFIG.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=RUNTIME_CONFIG.LOGGING_FILE_LEVEL,
        format=_lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
