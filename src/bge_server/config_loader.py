# ====== Code Summary ======
# Defines BgeServerConfig (env-based settings) and configures the loggerplusplus sinks for the
# BGE model-suite micro-service. This file is imported FIRST in entrypoint.py so that the class
# body registers the app root on sys.path before any `libs.*` or `backend.*` import is resolved.
#
# Single runtime config, no YAML — using the flat config_loader.py exception from python.md (same
# pattern as the sibling src/mcp/config_loader.py). No .env file is required at runtime; the
# service receives env vars directly from docker compose.

# ====== Standard Library Imports ======
import pathlib
import sys

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env
from loggerplusplus import formats as lpp_formats
from loggerplusplus import loggerplusplus

# ─── Reset logger before anything else ───
loggerplusplus.remove()

# ─── Optional DEV_MODE early logger ───
# DEV_MODE is read directly from os.environ (not via env()) because it must activate a temporary
# debug sink BEFORE the BgeServerConfig class is evaluated. This sink is removed immediately
# after and replaced by the real sinks below.
import os as _os

if _os.environ.get("DEV_MODE"):
    loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
    _dev_logger = loggerplusplus.bind(identifier="DEV")
    _dev_logger.warning(f"DEV MODE is activated !")
    loggerplusplus.remove()

del _os


class BgeServerConfig(EnvConfigLoader):
    """
    Environment-driven configuration for the BGE model-suite micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have
    safe defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── Paths & dirs ─────
    # Root of the bge_server application (this file's directory, i.e. src/bge_server/).
    PATH_ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent

    # Register the app root on sys.path so `from libs.*` and `from backend.*` resolve regardless
    # of how the entry point is invoked (uvicorn bge_server.entrypoint:app, pytest, direct run).
    sys.path.append(str(PATH_ROOT_DIR))

    # ───── Logging (mandatory 5 — drive the logging setup) ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

    # ───── BGE model identities ─────
    # HuggingFace model ID for the dense + sparse embedding model (BGEM3FlagModel).
    BGE_M3_MODEL: str = env("BGE_M3_MODEL", default="BAAI/bge-m3")
    # HuggingFace model ID for the cross-encoder reranker (FlagReranker).
    BGE_RERANKER_MODEL: str = env("BGE_RERANKER_MODEL", default="BAAI/bge-reranker-v2-m3")

    # ───── BGE model revision pins (supply-chain control) ─────
    # Commit sha each model is pinned to. BGEM3FlagModel/FlagReranker silently drop a `revision=`
    # kwarg (never forwarded to from_pretrained — see libs/bge_models/revision.py), so pinning
    # works by resolving the sha to a LOCAL snapshot path via huggingface_hub.snapshot_download
    # and loading from that path instead of the bare repo id.
    # Defaults are the `main`-branch head commit as of 2026-07-29 (`curl -s
    # https://huggingface.co/api/models/<repo> | jq .sha`) — a fresh deploy is pinned-by-default
    # but overridable. Set to "" (empty string) to opt back into the floating `main` behavior.
    BGE_M3_REVISION: str = env(
        "BGE_M3_REVISION", default="5617a9f61b028005a4858fdac845db406aefb181"
    )
    BGE_RERANKER_REVISION: str = env(
        "BGE_RERANKER_REVISION", default="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )

    # ───── BGE device policy ─────
    # Controls which compute device the models are loaded on.
    # "auto"  → prefer GPU if torch.cuda.is_available(), else fall back to CPU silently.
    # "cuda"  → require GPU; fail loud at load time if CUDA is not available (no silent fallback).
    # "cpu"   → always use CPU regardless of GPU availability.
    # DeviceResolver (libs/bge_models/device.py) translates this into a concrete device string.
    BGE_DEVICE: str = env("BGE_DEVICE", default="auto")

    # ───── BGE model runtime knobs ─────
    # Request fp16 precision. GATED: fp16 is only applied when the resolved device is "cuda".
    # If BGE_FP16=true but BGE_DEVICE resolves to "cpu", fp16 is forced off with a warning —
    # fp16 on CPU is not beneficial and may cause errors depending on the FlagEmbedding version.
    BGE_FP16: bool = env("BGE_FP16", cast=bool, default="false")
    # Maximum token length passed to FlagEmbedding's encode call. Default 2048 (was 8192): a single
    # oversized input at 8192 forces a full 8192-token transformer forward pass — a large transient
    # CPU + activation-RAM spike (a real OOM risk under the memory cap) and wasted work, since
    # contextualized chunks are far shorter. 2048 stays well above real chunk lengths; raise it only
    # if inputs are genuinely longer (embedding tokens beyond the chunk length yields nothing).
    BGE_M3_MAX_LENGTH: int = env("BGE_M3_MAX_LENGTH", cast=int, default="2048")

    # ───── Dynamic batching ─────
    # Maximum number of UNITS (texts for embed/sparse, query+text pairs for rerank) to include
    # in a single batch. A single request whose cost exceeds this limit is still admitted whole
    # and processed as a batch of one — FlagEmbedding handles its own internal chunking.
    # Effective range: 1..∞. With max_batch_size=1 + max_wait_ms=0 the engine degrades to
    # per-request processing (no batching overhead, useful for debugging or very low load).
    BGE_MAX_BATCH_SIZE: int = env("BGE_MAX_BATCH_SIZE", cast=int, default="32")
    # Batch formation window in milliseconds. After the first item arrives, the worker waits up
    # to this many ms for additional items before dispatching the batch. 0 = process immediately
    # with whatever is available (effectively disables wait-based batching).
    BGE_MAX_WAIT_MS: int = env("BGE_MAX_WAIT_MS", cast=int, default="10")
    # Maximum number of pending items in the per-op bounded queue. When full, submit() raises
    # QueueFullError and the router responds HTTP 503 with Retry-After: 1. Raise this on
    # high-traffic servers or lower it for tighter back-pressure control.
    BGE_MAX_QUEUE_SIZE: int = env("BGE_MAX_QUEUE_SIZE", cast=int, default="256")
    # Number of intra-op threads torch may use PER inference call (torch.set_num_threads).
    # 0 = auto: the service derives a reasonable value at startup as cpu_count/max_concurrency
    # (rounded up, minimum 1) so the combined thread budget stays near the total core count.
    # Set explicitly to override the auto derivation (e.g. BGE_TORCH_NUM_THREADS=4).
    BGE_TORCH_NUM_THREADS: int = env("BGE_TORCH_NUM_THREADS", cast=int, default="0")
    # Keep-warm interval in seconds. A background task runs a tiny forward pass on every model
    # (dense/sparse/rerank) every this-many seconds so their weights stay RESIDENT: on a
    # memory-constrained host the OS pages out an idle process's ~GB working set, and the next real
    # request then pays a 30-50 s page-in ("cold load"). That cold load occupies the single rerank
    # worker long enough that concurrent callers time out and re-enqueue, cascading. A cheap
    # periodic touch (~0.3 s of compute) prevents the eviction entirely. 0 = disabled.
    BGE_KEEPWARM_SECONDS: int = env("BGE_KEEPWARM_SECONDS", cast=int, default="45")

    # ───── Request size ceilings (edge validation, before the batching engine) ─────
    # A single oversized request is still admitted "whole" by BatchQueueWorker and holds the
    # shared model lock for its entire duration (see libs/batching/worker.py). These ceilings
    # reject such requests at the Pydantic layer (HTTP 422) instead of letting them stall every
    # other collection's embed/rerank traffic. Defaults scale off the batching/model knobs above
    # so they don't silently drift out of sync when those are tuned.
    #
    # Max number of items per request (inputs for /embed·/embed_sparse·/embed_colbert, texts for
    # /rerank). Default is 16x BGE_MAX_BATCH_SIZE: generous headroom over the DocForge embed node's
    # own client-side batch_size (default 32, see shared_libs embed/base/config.py) while still
    # bounding a misconfigured/unbounded caller.
    BGE_MAX_REQUEST_ITEMS: int = env(
        "BGE_MAX_REQUEST_ITEMS", cast=int, default=str(BGE_MAX_BATCH_SIZE * 16)
    )
    # Max characters per individual text (each /embed·/embed_sparse·/embed_colbert item, each
    # /rerank text or query). Default is 8x BGE_M3_MAX_LENGTH (tokens): truncate=True only
    # truncates AFTER tokenization, so an unbounded string still pays full tokenizer cost — this
    # caps that cost independently of the token truncation.
    BGE_MAX_TEXT_CHARS: int = env(
        "BGE_MAX_TEXT_CHARS", cast=int, default=str(BGE_M3_MAX_LENGTH * 8)
    )

    @classmethod
    def validate(cls) -> None:
        """
        Validate env-derived config values beyond simple type casting.

        Raises:
            ValueError: When BGE_DEVICE is not one of the accepted policy values, or when
                any of the batching knobs has a value that would make the engine behave
                incorrectly (e.g. zero or negative batch size / queue size).
        """
        super().validate()
        # Import here to avoid a circular dep at class-body evaluation time;
        # VALID_BGE_DEVICE_POLICIES is a plain frozenset with no ML deps.
        from libs.bge_models.device import VALID_BGE_DEVICE_POLICIES  # noqa: PLC0415

        if cls.BGE_DEVICE not in VALID_BGE_DEVICE_POLICIES:
            raise ValueError(
                f"BGE_DEVICE='{cls.BGE_DEVICE}' is not a valid device policy. "
                f"Accepted values: {sorted(VALID_BGE_DEVICE_POLICIES)}"
            )
        if cls.BGE_MAX_BATCH_SIZE < 1:
            raise ValueError(f"BGE_MAX_BATCH_SIZE must be >= 1, got {cls.BGE_MAX_BATCH_SIZE}")
        if cls.BGE_MAX_WAIT_MS < 0:
            raise ValueError(f"BGE_MAX_WAIT_MS must be >= 0, got {cls.BGE_MAX_WAIT_MS}")
        if cls.BGE_MAX_QUEUE_SIZE < 1:
            raise ValueError(f"BGE_MAX_QUEUE_SIZE must be >= 1, got {cls.BGE_MAX_QUEUE_SIZE}")
        if cls.BGE_MAX_REQUEST_ITEMS < 1:
            raise ValueError(f"BGE_MAX_REQUEST_ITEMS must be >= 1, got {cls.BGE_MAX_REQUEST_ITEMS}")
        if cls.BGE_MAX_TEXT_CHARS < 1:
            raise ValueError(f"BGE_MAX_TEXT_CHARS must be >= 1, got {cls.BGE_MAX_TEXT_CHARS}")
        if cls.BGE_KEEPWARM_SECONDS < 0:
            raise ValueError(f"BGE_KEEPWARM_SECONDS must be >= 0, got {cls.BGE_KEEPWARM_SECONDS}")


# ─── Apply logging configuration AFTER class definition ───
_lpp_format_cls = getattr(lpp_formats, BgeServerConfig.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat)
_lpp_format = _lpp_format_cls()

if BgeServerConfig.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=BgeServerConfig.LOGGING_CONSOLE_LEVEL,
        format=_lpp_format,
    )

if BgeServerConfig.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=BgeServerConfig.LOGGING_FILE_LEVEL,
        format=_lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
