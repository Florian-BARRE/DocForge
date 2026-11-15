# ====== Code Summary ======
# ServerConfig: the runtime configuration shared by every DocForge model-host micro-service (bge,
# paddle, mineru, dots_ocr). It is a configplusplus static class: every value is read from the
# environment ONCE, when the class body is evaluated, then injected (as the class itself) into the
# objects that need it. A server subclasses it to add its own fields, and may re-declare a base field
# under its historical, prefixed variable name (e.g. `MAX_BODY_BYTES = env("PADDLE_MAX_BODY_BYTES", ...)`).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Final

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env

# ====== Constants ======
VALID_DEVICE_POLICIES: Final[frozenset[str]] = frozenset({"auto", "cpu", "cuda"})
_MAX_TCP_PORT: Final[int] = 65_535


class ServerConfig(EnvConfigLoader):
    """Environment-driven configuration common to every model-host micro-service.

    All attributes are read from the environment when the class body is evaluated and have a safe
    default, so a container starts without any `.env` file. Subclasses add their own attributes;
    `validate()` is called once by the server lifespan, before any slow model load.

    Attributes:
        DEV_MODE (bool): Activates the early debug logger (see `LoggingBootstrap`).
        LOGGING_CONSOLE_LEVEL (str): Minimum level of the console sink.
        LOGGING_FILE_LEVEL (str): Minimum level of the file sink.
        LOGGING_ENABLE_CONSOLE (bool): Whether the console sink is added.
        LOGGING_ENABLE_FILE (bool): Whether the rotating file sink is added.
        LOGGING_LPP_FORMAT (str): Name of a `loggerplusplus.formats` class (`ShortFormat`...).
        SERVER_HOST (str): Interface the ASGI server binds to.
        SERVER_PORT (int): TCP port the ASGI server listens on.
        MAX_BODY_BYTES (int): Hard ceiling on a raw request body (413 above it).
        LOCK_WAIT_TIMEOUT_SECONDS (float): Max wait for the model lock before a 503 back-pressure.
        GZIP_MINIMUM_SIZE (int): Responses below this size (bytes) skip gzip compression.
        DEVICE (str): Device policy, one of `VALID_DEVICE_POLICIES`.
        NUM_THREADS (int): CPU thread budget for inference; 0 means "resolve from the CPU budget".
    """

    # ───── Mode ─────
    DEV_MODE: bool = env("DEV_MODE", cast=bool, default="false")

    # ───── Logging ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

    # ───── Network ─────
    SERVER_HOST: str = env("SERVER_HOST", default="0.0.0.0")
    SERVER_PORT: int = env("SERVER_PORT", cast=int, default="80")

    # ───── Request limits ─────
    # 100 MiB is generous for real scans/PDFs; a model host's memory ceiling exists for model spikes,
    # not for attacker payloads.
    MAX_BODY_BYTES: int = env("MAX_BODY_BYTES", cast=int, default="104857600")
    # PaddlePaddle / VLM inference is not safe to run concurrently, so a request waits at most this
    # long for the model lock before the route answers 503.
    LOCK_WAIT_TIMEOUT_SECONDS: float = env("LOCK_WAIT_TIMEOUT_SECONDS", cast=float, default="290")
    # Below this response size gzip's CPU cost is not worth the saved bandwidth.
    GZIP_MINIMUM_SIZE: int = env("GZIP_MINIMUM_SIZE", cast=int, default="1024")

    # ───── Device and threads ─────
    # "auto" prefers a GPU when one is visible, "cuda" requires it, "cpu" never uses it.
    DEVICE: str = env("DEVICE", default="auto")
    NUM_THREADS: int = env("NUM_THREADS", cast=int, default="0")

    @classmethod
    def validate(cls) -> None:
        """Validate the values beyond their type cast, failing fast with a precise cause.

        Raises:
            ValueError: When the port, a limit, the timeout, the device policy or the thread budget
                is out of range.
        """
        super().validate()
        if not 1 <= cls.SERVER_PORT <= _MAX_TCP_PORT:
            raise ValueError(f"SERVER_PORT must be in 1..{_MAX_TCP_PORT}, got {cls.SERVER_PORT}")
        if cls.MAX_BODY_BYTES < 1:
            raise ValueError(f"MAX_BODY_BYTES must be >= 1, got {cls.MAX_BODY_BYTES}")
        if cls.LOCK_WAIT_TIMEOUT_SECONDS <= 0:
            raise ValueError(
                f"LOCK_WAIT_TIMEOUT_SECONDS must be > 0, got {cls.LOCK_WAIT_TIMEOUT_SECONDS}"
            )
        if cls.GZIP_MINIMUM_SIZE < 0:
            raise ValueError(f"GZIP_MINIMUM_SIZE must be >= 0, got {cls.GZIP_MINIMUM_SIZE}")
        if cls.DEVICE not in VALID_DEVICE_POLICIES:
            raise ValueError(
                f"DEVICE='{cls.DEVICE}' is not a valid device policy. "
                f"Accepted values: {sorted(VALID_DEVICE_POLICIES)}"
            )
        if cls.NUM_THREADS < 0:
            raise ValueError(f"NUM_THREADS must be >= 0, got {cls.NUM_THREADS}")
