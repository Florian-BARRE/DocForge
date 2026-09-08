# ====== Code Summary ======
# Defines MineruServerConfig (env-based settings) and configures the loggerplusplus sinks for the
# MinerU2.5-Pro VLM layout-parsing micro-service. This file is imported FIRST in entrypoint.py so that
# the class body registers the app root on sys.path before any `libs.*` or `backend.*` import is
# resolved.
#
# Single runtime config, no YAML — using the flat config_loader.py exception from python.md (same
# pattern as the sibling src/paddle_server/config_loader.py and src/bge_server/config_loader.py). No
# .env file is required at runtime; the service receives env vars directly from docker compose.

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
# debug sink BEFORE the MineruServerConfig class is evaluated. This sink is removed immediately after
# and replaced by the real sinks below.
import os as _os

if _os.environ.get("DEV_MODE"):
    loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
    _dev_logger = loggerplusplus.bind(identifier="DEV")
    _dev_logger.warning(f"DEV MODE is activated !")
    loggerplusplus.remove()

del _os


class MineruServerConfig(EnvConfigLoader):
    """
    Environment-driven configuration for the MinerU2.5-Pro VLM layout-parsing micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have safe
    defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── Paths & dirs ─────
    # Root of the mineru_server application (this file's directory, i.e. src/mineru_server/).
    PATH_ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent

    # Register the app root on sys.path so `from libs.*` and `from backend.*` resolve regardless of
    # how the entry point is invoked (uvicorn entrypoint:app, pytest, direct run).
    sys.path.append(str(PATH_ROOT_DIR))

    # ───── Logging (mandatory 5 — drive the logging setup) ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

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
    # (only needs mineru[core]); "vlm-vllm-engine" / "vlm-sglang-engine" are faster but pull the heavy
    # vllm/sglang stacks — opt into them at deploy time (add the extra + flip this var). GPU-only in
    # every case: the MinerU2.5-Pro VLM requires CUDA (see the module + Dockerfile notes).
    MINERU_BACKEND: str = env("MINERU_BACKEND", default="vlm-transformers")
    # Default OCR/parse language hint forwarded to MinerU ("ch" auto-handles latin scripts too). This
    # only steers MinerU's own text post-processing; the IR language is detected downstream by the
    # DocForge docmeta/language node, not here.
    MINERU_LANG: str = env("MINERU_LANG", default="ch")

    # ───── Request limits ─────
    # Hard ceiling (BYTES) on a request body the /parse route will buffer. The route reads the whole
    # body into memory (the body IS the PDF), so without a cap a multi-GB upload OOMs this container. A
    # declared Content-Length over the cap is rejected 413 before a byte is read; the streamed read is
    # capped too, so a lying/absent length can't bypass it. 100 MiB is generous for real scans/PDFs.
    MINERU_MAX_BODY_BYTES: int = env("MINERU_MAX_BODY_BYTES", cast=int, default=104_857_600)

    # ───── Concurrency ─────
    # MinerU VLM inference is memory-heavy (min 8 GB VRAM) and not safe to run concurrently on one GPU,
    # so every /parse call is serialized behind a single asyncio.Lock. This is the max time a request
    # waits to acquire that lock before the router returns HTTP 503 (back-pressure) instead of piling
    # up unbounded. Defaults high — a VLM parse of a multi-page document is minutes, not seconds.
    MINERU_LOCK_WAIT_TIMEOUT_SECONDS: float = env(
        "MINERU_LOCK_WAIT_TIMEOUT_SECONDS", cast=float, default="590"
    )

    # ───── GPU gate ─────
    # MinerU2.5-Pro's VLM backend requires CUDA — CPU is unsupported and would either fail at model
    # load or run pathologically slow/wrong. When True (default), /health reports UNHEALTHY on a host
    # with no visible CUDA device so the container never advertises a readiness it cannot honor. Set
    # False only for a deliberate CPU smoke-test of the wiring (never for real parsing).
    MINERU_REQUIRE_GPU: bool = env("MINERU_REQUIRE_GPU", cast=bool, default="true")

    @classmethod
    def validate(cls) -> None:
        """
        Validate env-derived config values beyond simple type casting.

        Raises:
            ValueError: When MINERU_LOCK_WAIT_TIMEOUT_SECONDS is not strictly positive.
        """
        super().validate()
        if cls.MINERU_LOCK_WAIT_TIMEOUT_SECONDS <= 0:
            raise ValueError(
                f"MINERU_LOCK_WAIT_TIMEOUT_SECONDS must be > 0, got "
                f"{cls.MINERU_LOCK_WAIT_TIMEOUT_SECONDS}"
            )


# ─── Apply logging configuration AFTER class definition ───
_lpp_format_cls = getattr(
    lpp_formats, MineruServerConfig.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat
)
_lpp_format = _lpp_format_cls()

if MineruServerConfig.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=MineruServerConfig.LOGGING_CONSOLE_LEVEL,
        format=_lpp_format,
    )

if MineruServerConfig.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=MineruServerConfig.LOGGING_FILE_LEVEL,
        format=_lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
