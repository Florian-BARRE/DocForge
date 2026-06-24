# ====== Code Summary ======
# Defines BaseRuntimeConfig — the SHARED env-based settings + loggerplusplus sink setup
# needed by the common_libs (storage, providers, search, pipeline stages…). Both apps
# subclass it: app/config and worker/config add their own dedicated variables on top.
# This base must be importable before any common_libs import.

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
# DEV_MODE is read directly from os.environ (not via env()) because it must activate a
# temporary debug sink BEFORE the config class is evaluated. Removed immediately after.
if os.environ.get("DEV_MODE"):
    loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
    _dev_logger = loggerplusplus.bind(identifier="DEV")
    _dev_logger.warning(f"DEV MODE is activated !")
    loggerplusplus.remove()


class BaseRuntimeConfig(EnvConfigLoader):
    """
    Shared runtime configuration consumed by the common_libs and inherited by both apps.

    Holds only the variables the SHARED code needs (storage, providers, observability
    heartbeat, pipeline stage defaults…). Web-only and worker-only variables live in the
    per-app subclasses (app/config/RUNTIME_CONFIG, worker/config/RUNTIME_CONFIG).
    """

    # ───── Paths & dirs ─────
    # Root of the SHARED tree (src/docforge/common/). This file lives at
    # common/base_config/runtime/base_config.py → parent×3 = common/.
    PATH_COMMON_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent

    # Register the common root on sys.path so the shared packages resolve
    # (`from common_libs.<bucket> import …`). The per-app entrypoints also add this +
    # their own dir before importing config, so this is a defensive belt-and-suspenders.
    sys.path.append(str(PATH_COMMON_DIR))

    # ───── Logging (ALWAYS present in every project) ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

    # ───── Database (PostgreSQL) ─────
    POSTGRES_USER: str = env("POSTGRES_USER", default="docforge")
    POSTGRES_PASSWORD: str = env("POSTGRES_PASSWORD")
    POSTGRES_HOST: str = env("POSTGRES_HOST", default="localhost")
    POSTGRES_PORT: int = env("POSTGRES_PORT", cast=int, default="5432")
    POSTGRES_DB: str = env("POSTGRES_DB", default="docforge")

    # ───── Object store (SeaweedFS — S3-compatible API, port 8333) ─────
    S3_ENDPOINT_URL: str = env("S3_ENDPOINT_URL", default="http://localhost:8333")
    S3_ACCESS_KEY: str = env("S3_ACCESS_KEY", default="seaweedfs_admin")
    S3_SECRET_KEY: str = env("S3_SECRET_KEY")
    S3_BUCKET: str = env("S3_BUCKET", default="docforge-objects")
    S3_REGION: str = env("S3_REGION", default="us-east-1")
    # External-facing S3 URL for presigned URLs (empty = use S3_ENDPOINT_URL as-is).
    S3_PUBLIC_URL: str = env("S3_PUBLIC_URL", default="", required=False)

    # ───── Gotenberg (document conversion — worker S0/S1 + app health check) ─────
    GOTENBERG_URL: str = env("GOTENBERG_URL", default="http://localhost:3000")
    GOTENBERG_TIMEOUT_S: int = env("GOTENBERG_TIMEOUT_S", cast=int, default="120")

    # ───── Pipeline providers ─────
    PARSER_DEFAULT_BACKEND: str = env("PARSER_DEFAULT_BACKEND", default="docling")
    DOCLING_USE_GPU: bool = env("DOCLING_USE_GPU", cast=bool, default="false")

    # ───── Redis (arq job queue — app enqueues, worker consumes) ─────
    REDIS_URL: str = env("REDIS_URL", default="redis://localhost:6379")

    # ───── Observability heartbeat (worker writes, app reads) ─────
    OBS_HEARTBEAT_INTERVAL_S: int = env("OBS_HEARTBEAT_INTERVAL_S", cast=int, default="5")
    OBS_HEARTBEAT_TTL_S: int = env("OBS_HEARTBEAT_TTL_S", cast=int, default="15")

    # ───── P3 — S2 Enrichment (OCR / VLM / classifier) ─────
    # Read by both apps via provider-config merge_defaults() (ingestion AND validation).
    CLASSIFIER_TYPE: str = env("CLASSIFIER_TYPE", default="layout_labels")
    CLASSIFIER_ONNX_MODEL_PATH: str = env(
        "CLASSIFIER_ONNX_MODEL_PATH", default="models/classifier.onnx"
    )
    CLASSIFIER_USE_GPU: bool = env("CLASSIFIER_USE_GPU", cast=bool, default="false")

    OCR_PADDLE_ENABLED: bool = env("OCR_PADDLE_ENABLED", cast=bool, default="false")
    OCR_PADDLE_USE_GPU: bool = env("OCR_PADDLE_USE_GPU", cast=bool, default="false")

    MISTRAL_OCR_ENABLED: bool = env("MISTRAL_OCR_ENABLED", cast=bool, default="false")
    MISTRAL_OCR_API_URL: str = env("MISTRAL_OCR_API_URL", default="https://api.mistral.ai/v1")
    MISTRAL_OCR_API_KEY: str = env("MISTRAL_OCR_API_KEY", default="")
    MISTRAL_OCR_MODEL: str = env("MISTRAL_OCR_MODEL", default="mistral-ocr-latest")
    MISTRAL_OCR_TIMEOUT_S: int = env("MISTRAL_OCR_TIMEOUT_S", cast=int, default="60")

    VLM_ENABLED: bool = env("VLM_ENABLED", cast=bool, default="false")
    VLM_API_BASE_URL: str = env("VLM_API_BASE_URL", default="http://localhost:8080/v1")
    VLM_API_KEY: str = env("VLM_API_KEY", default="local")
    VLM_MODEL: str = env("VLM_MODEL", default="Qwen/Qwen2.5-VL-7B-Instruct")
    VLM_TIMEOUT_S: int = env("VLM_TIMEOUT_S", cast=int, default="120")
    VLM_MAX_TOKENS: int = env("VLM_MAX_TOKENS", cast=int, default="512")
    VLM_COST_PER_CALL: float = env("VLM_COST_PER_CALL", cast=float, default="0.0")

    OCR_CONFIDENCE_THRESHOLD: float = env("OCR_CONFIDENCE_THRESHOLD", cast=float, default="0.85")
    ENRICH_MAX_BUDGET_USD: float = env("ENRICH_MAX_BUDGET_USD", cast=float, default="0.0")

    # ───── P4 — S4 Chunking ─────
    CHUNK_MAX_TOKENS: int = env("CHUNK_MAX_TOKENS", cast=int, default="512")
    CHUNK_OVERLAP_BLOCKS: int = env("CHUNK_OVERLAP_BLOCKS", cast=int, default="0")

    # ───── P4 — S6 Embedding + Indexing (query-time AND ingestion) ─────
    TEI_BASE_URL: str = env("TEI_BASE_URL", default="http://localhost:8080")
    TEI_BATCH_SIZE: int = env("TEI_BATCH_SIZE", cast=int, default="64")
    # False for a dense-only BGE-M3 deployment (no sparse head) — otherwise /embed_sparse
    # returns HTTP 424 and breaks query embedding + chunk/metadata re-embed.
    TEI_EMBED_SPARSE: bool = env("TEI_EMBED_SPARSE", cast=bool, default="True")

    # OpenAI / OpenAI-compatible cloud embed provider (ingestion S6 + query-time).
    OPENAI_API_KEY: str = env("OPENAI_API_KEY", required=False, default="")
    EMBED_API_KEY: str = env("EMBED_API_KEY", required=False, default="")

    # ───── Qdrant vector store (app search + worker S6 index) ─────
    QDRANT_HOST: str = env("QDRANT_HOST", default="localhost")
    QDRANT_PORT: int = env("QDRANT_PORT", cast=int, default="6333")
    QDRANT_API_KEY: str = env("QDRANT_API_KEY", default="")
    QDRANT_HTTPS: bool = env("QDRANT_HTTPS", cast=bool, default="false")

    # ───── Search pipeline — reranker (consumed by rerank config merge_defaults) ─────
    BGE_RERANKER_URL: str = env("BGE_RERANKER_URL", required=False, default="http://reranker:80")
    BGE_RERANKER_BATCH_SIZE: int = env("BGE_RERANKER_BATCH_SIZE", cast=int, default="32")
    COHERE_API_KEY: str = env("COHERE_API_KEY", required=False, default="")

    # ───── Search pipeline — query transform LLM (consumed by LLM config merge_defaults) ─────
    LLM_API_BASE_URL: str = env("LLM_API_BASE_URL", required=False, default="http://localhost:8080/v1")
    LLM_API_KEY: str = env("LLM_API_KEY", required=False, default="local")
    LLM_MODEL: str = env("LLM_MODEL", required=False, default="Qwen/Qwen2.5-7B-Instruct")


# ─── Apply logging configuration AFTER class definition (runs once, on first import) ───
_lpp_format_cls = getattr(lpp_formats, BaseRuntimeConfig.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat)
_lpp_format = _lpp_format_cls()

if BaseRuntimeConfig.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=BaseRuntimeConfig.LOGGING_CONSOLE_LEVEL,
        format=_lpp_format,
    )

if BaseRuntimeConfig.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=BaseRuntimeConfig.LOGGING_FILE_LEVEL,
        format=_lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
