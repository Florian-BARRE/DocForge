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
    # Maximum token length passed to FlagEmbedding's encode call.
    BGE_M3_MAX_LENGTH: int = env("BGE_M3_MAX_LENGTH", cast=int, default="8192")

    @classmethod
    def validate(cls) -> None:
        """
        Validate env-derived config values beyond simple type casting.

        Raises:
            ValueError: When BGE_DEVICE is not one of the accepted policy values.
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
