# ====== Code Summary ======
# MineruServerConfig: the env-based settings of the MinerU2.5-Pro VLM layout-parsing micro-service. It
# extends the shared model_server_core ServerConfig (logging, host/port, DEV_MODE, gzip floor, request
# ceiling, lock-wait timeout), re-declaring the base fields the service has always read under a MINERU_*
# name, and adds the MinerU-specific knobs (backend, language, model cache, GPU gate). The logging sinks
# are applied by the core's ServerEntrypoint, not at import time.
#
# Single runtime config, no YAML. No .env file is required at runtime; the service receives env vars
# directly from docker compose.

# ====== Third-Party Library Imports ======
from configplusplus import env
from model_server_core import ServerConfig


class MineruServerConfig(ServerConfig):
    """
    Environment-driven configuration for the MinerU2.5-Pro VLM layout-parsing micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have safe
    defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── Model cache ─────
    # MinerU resolves its VLM weights (MinerU2.5-Pro-2605-1.2B + the layout/OCR helpers) from the
    # configured model source on first parse and caches them under MINERU_MODEL_SOURCE's cache root.
    # Mounted as a named volume in compose so weights persist across container recreations (mirrors
    # bge_server's HF_HOME and paddle_server's PADDLE_PDX_CACHE_HOME). MinerU reads HF_HOME/MODELSCOPE
    # itself; this value is surfaced in the boot log and used to pre-create the mount point.
    MINERU_MODEL_CACHE_HOME: str = env("MINERU_MODEL_CACHE_HOME", default="/models")
    # Model hoster MinerU downloads weights from: "huggingface" (default) or "modelscope". MinerU
    # reads the env var MINERU_MODEL_SOURCE directly; declared here to surface it in the boot log.
    MINERU_MODEL_SOURCE: str = env("MINERU_MODEL_SOURCE", default="huggingface")
    # The MinerU VLM backend that runs the parse. "vlm-transformers" is the dependency-light default
    # (only needs mineru[vlm,pipeline,api]); "vlm-vllm-engine" / "vlm-sglang-engine" are faster but
    # pull the heavy vllm/sglang stacks — opt into them at deploy time (add the extra + flip this
    # var). GPU-only in every case: the MinerU2.5-Pro VLM requires CUDA (see the module + Dockerfile
    # notes).
    MINERU_BACKEND: str = env("MINERU_BACKEND", default="vlm-transformers")
    # Default OCR/parse language hint forwarded to MinerU ("ch" auto-handles latin scripts too). This
    # only steers MinerU's own text post-processing; the IR language is detected downstream by the
    # DocForge docmeta/language node, not here.
    MINERU_LANG: str = env("MINERU_LANG", default="ch")

    # ───── Request limits (the core's MAX_BODY_BYTES, kept under its historical variable name) ─────
    # Hard ceiling (BYTES) on a request body the /parse route will buffer. The route reads the whole
    # body into memory (the body IS the PDF), so without a cap a multi-GB upload OOMs this container. A
    # declared Content-Length over the cap is rejected 413 before a byte is read; the streamed read is
    # capped too, so a lying/absent length can't bypass it. 100 MiB is generous for real scans/PDFs.
    MAX_BODY_BYTES: int = env("MINERU_MAX_BODY_BYTES", cast=int, default="104857600")

    # ───── Concurrency (the core's LOCK_WAIT_TIMEOUT_SECONDS, kept under its historical name) ─────
    # MinerU VLM inference is memory-heavy (min 8 GB VRAM) and not safe to run concurrently on one GPU,
    # so every /parse call is serialized behind a single asyncio.Lock. This is the max time a request
    # waits to acquire that lock before the router returns HTTP 503 (back-pressure) instead of piling
    # up unbounded. Defaults high — a VLM parse of a multi-page document is minutes, not seconds.
    LOCK_WAIT_TIMEOUT_SECONDS: float = env(
        "MINERU_LOCK_WAIT_TIMEOUT_SECONDS", cast=float, default="590"
    )

    # ───── GPU gate ─────
    # MinerU2.5-Pro's VLM backend requires CUDA — CPU is unsupported and would either fail at model
    # load or run pathologically slow/wrong. When True (default), /health reports UNHEALTHY on a host
    # with no visible CUDA device so the container never advertises a readiness it cannot honor. Set
    # False only for a deliberate CPU smoke-test of the wiring (never for real parsing).
    MINERU_REQUIRE_GPU: bool = env("MINERU_REQUIRE_GPU", cast=bool, default="true")
