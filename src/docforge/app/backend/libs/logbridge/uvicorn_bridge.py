# ====== Code Summary ======
# UvicornLogBridge — routes uvicorn's stdlib loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`)
# through loggerplusplus so the server's own access/error lines carry the SAME format and correlation
# id as the rest of the app, instead of uvicorn's default off-format output that bypasses the sinks.
# It replaces each uvicorn logger's handlers with the shared LoggingInterceptHandler and stops their
# propagation to the root logger (so a record is rendered once, by loggerplusplus). Configured here
# in application code — never via log flags baked into the Dockerfile CMD — so one code path owns it.

# ====== Standard Library Imports ======
import logging

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .intercept_handler import LoggingInterceptHandler

# The uvicorn stdlib loggers whose records must be re-emitted through loggerplusplus.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")


class UvicornLogBridge:
    """Static helper that redirects uvicorn's stdlib loggers into loggerplusplus."""

    logger = loggerplusplus.bind(identifier="UvicornLogBridge")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("UvicornLogBridge is a static-only class and cannot be instantiated.")

    @classmethod
    def install(cls) -> None:
        """
        Route uvicorn's `uvicorn` / `uvicorn.access` / `uvicorn.error` loggers into loggerplusplus.

        Idempotent: each target logger's handlers are replaced with a single intercept handler and
        propagation is disabled, so a record is rendered exactly once (by loggerplusplus) with the
        app's format + correlation id. Safe to call once at startup.
        """
        # 1. Build one shared intercept handler for every uvicorn logger.
        handler = LoggingInterceptHandler()

        # 2. Point each uvicorn logger at it and stop propagation to the root (no double render).
        for name in _UVICORN_LOGGERS:
            uvicorn_logger = logging.getLogger(name)
            uvicorn_logger.handlers = [handler]
            uvicorn_logger.propagate = False

        cls.logger.info(f"Uvicorn loggers routed through loggerplusplus")


__all__ = ["UvicornLogBridge"]
