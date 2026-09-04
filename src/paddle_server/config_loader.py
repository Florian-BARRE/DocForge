# ====== Code Summary ======
# Defines PaddleServerConfig (env-based settings) and configures the loggerplusplus sinks for
# the PP-StructureV3 layout-parsing micro-service. This file is imported FIRST in entrypoint.py
# so that the class body registers the app root on sys.path before any `libs.*` or `backend.*`
# import is resolved.
#
# Single runtime config, no YAML — using the flat config_loader.py exception from python.md (same
# pattern as the sibling src/bge_server/config_loader.py). No .env file is required at runtime;
# the service receives env vars directly from docker compose.

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
# debug sink BEFORE the PaddleServerConfig class is evaluated. This sink is removed immediately
# after and replaced by the real sinks below.
import os as _os

if _os.environ.get("DEV_MODE"):
    loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
    _dev_logger = loggerplusplus.bind(identifier="DEV")
    _dev_logger.warning(f"DEV MODE is activated !")
    loggerplusplus.remove()

del _os


class PaddleServerConfig(EnvConfigLoader):
    """
    Environment-driven configuration for the PP-StructureV3 layout-parsing micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have
    safe defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── Paths & dirs ─────
    # Root of the paddle_server application (this file's directory, i.e. src/paddle_server/).
    PATH_ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent

    # Register the app root on sys.path so `from libs.*` and `from backend.*` resolve regardless
    # of how the entry point is invoked (uvicorn entrypoint:app, pytest, direct run).
    sys.path.append(str(PATH_ROOT_DIR))

    # ───── Logging (mandatory 5 — drive the logging setup) ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

    # ───── Model cache ─────
    # PaddleX resolves every inference model (layout/OCR/table/formula/seal) to a tarball fetched
    # from the configured model hoster on first use and cached under
    # ``{PADDLE_PDX_CACHE_HOME}/official_models`` (paddlex.utils.cache.CACHE_DIR /
    # paddlex.inference.utils.official_models._save_dir — verified against the paddlex 3.7.0
    # wheel source, NOT documented in the pipeline usage tutorials). Mounted as a named volume in
    # compose so weights persist across container recreations (mirrors bge_server's HF_HOME).
    PADDLE_PDX_CACHE_HOME: str = env("PADDLE_PDX_CACHE_HOME", default="/models")
    # Model hoster: "huggingface" (default, needs huggingface.co resolution — same DNS pin as
    # bge_server) or "bos"/"aistudio"/"modelscope". Read here only to surface it in the boot log;
    # PaddleX itself reads the env var directly (paddlex.utils.flags.MODEL_SOURCE).
    PADDLE_PDX_MODEL_SOURCE: str = env("PADDLE_PDX_MODEL_SOURCE", default="huggingface")

    # ───── Request limits ─────
    # Hard ceiling (BYTES) on a request body the /ocr and /layout-parsing routes will buffer. Both
    # read the whole body into memory (the body IS the image/PDF), so without a cap a multi-GB upload
    # OOMs this container (whose memory ceiling exists for model spikes, not attacker payloads). A
    # declared Content-Length over the cap is rejected 413 before a byte is read; the streamed read is
    # capped too, so a lying/absent length can't bypass it. 100 MiB is generous for real scans/PDFs.
    PADDLE_MAX_BODY_BYTES: int = env("PADDLE_MAX_BODY_BYTES", cast=int, default=104_857_600)

    # ───── PP-StructureV3 sub-pipeline toggles (lean default) ─────
    # Mandatory sub-pipelines (layout detection + general OCR) are always on — PaddleX has no
    # toggle for them. These four are the OPTIONAL sub-pipelines; env-driven so the same image
    # runs lean or full without a rebuild.
    PADDLE_USE_TABLE_RECOGNITION: bool = env(
        "PADDLE_USE_TABLE_RECOGNITION", cast=bool, default="true"
    )
    PADDLE_USE_FORMULA_RECOGNITION: bool = env(
        "PADDLE_USE_FORMULA_RECOGNITION", cast=bool, default="false"
    )
    PADDLE_USE_SEAL_RECOGNITION: bool = env(
        "PADDLE_USE_SEAL_RECOGNITION", cast=bool, default="false"
    )
    PADDLE_USE_DOC_ORIENTATION_CLASSIFY: bool = env(
        "PADDLE_USE_DOC_ORIENTATION_CLASSIFY", cast=bool, default="false"
    )
    # Kept OFF always (not just default) per the mapper's provenance contract — see
    # libs/ppstructure/service.py. Exposed as an env var only so a deployment can flip it back on
    # deliberately; the request-level knob in the API schema is documented as always False.
    PADDLE_USE_DOC_UNWARPING: bool = env("PADDLE_USE_DOC_UNWARPING", cast=bool, default="false")

    # ───── PaddleOCR (OCR-only pipeline) ─────
    # The OCR-only capability runs a SEPARATE PaddleOCR (text detection + recognition) instance,
    # independent of the PP-StructureV3 layout pipeline above. These knobs are set at build time
    # (no request-level override), so the same image runs any language without a rebuild.
    # Recognition language pack (e.g. "en", "fr", "ch") — selects the det+rec model pair.
    PADDLE_OCR_LANG: str = env("PADDLE_OCR_LANG", default="en")
    # Run the textline-orientation classifier before recognition — helps rotated lines at the cost
    # of an extra model + latency. OFF by default (born-digital crops are upright).
    PADDLE_OCR_USE_TEXTLINE_ORIENTATION: bool = env(
        "PADDLE_OCR_USE_TEXTLINE_ORIENTATION", cast=bool, default="false"
    )

    # ───── Concurrency ─────
    # PaddlePaddle inference is not thread-safe; every /layout-parsing call is serialized behind
    # a single asyncio.Lock (libs/ppstructure/service.py). This is the max time a request waits
    # to acquire that lock before the router returns HTTP 503 (back-pressure, same shape as
    # bge_server's queue-full 503) instead of piling up unbounded.
    PADDLE_LOCK_WAIT_TIMEOUT_SECONDS: float = env(
        "PADDLE_LOCK_WAIT_TIMEOUT_SECONDS", cast=float, default="290"
    )

    @classmethod
    def validate(cls) -> None:
        """
        Validate env-derived config values beyond simple type casting.

        Raises:
            ValueError: When PADDLE_LOCK_WAIT_TIMEOUT_SECONDS is not strictly positive.
        """
        super().validate()
        if cls.PADDLE_LOCK_WAIT_TIMEOUT_SECONDS <= 0:
            raise ValueError(
                f"PADDLE_LOCK_WAIT_TIMEOUT_SECONDS must be > 0, got "
                f"{cls.PADDLE_LOCK_WAIT_TIMEOUT_SECONDS}"
            )


# ─── Apply logging configuration AFTER class definition ───
_lpp_format_cls = getattr(
    lpp_formats, PaddleServerConfig.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat
)
_lpp_format = _lpp_format_cls()

if PaddleServerConfig.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=PaddleServerConfig.LOGGING_CONSOLE_LEVEL,
        format=_lpp_format,
    )

if PaddleServerConfig.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=PaddleServerConfig.LOGGING_FILE_LEVEL,
        format=_lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
