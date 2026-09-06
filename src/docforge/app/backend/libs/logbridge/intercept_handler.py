# ====== Code Summary ======
# LoggingInterceptHandler — a stdlib logging.Handler that forwards every record emitted through the
# standard `logging` module into loggerplusplus (loguru under the hood). This is the bridge that lets
# libraries which log via stdlib (uvicorn's `uvicorn` / `uvicorn.access` / `uvicorn.error` loggers) be
# rendered with the SAME loggerplusplus format — and carry the correlation id the app's loguru patcher
# stamps — instead of escaping in uvicorn's own off-format lines. It is the canonical loguru-recommended
# intercept, adapted to go through loggerplusplus rather than importing loguru directly.

# ====== Standard Library Imports ======
import logging

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class LoggingInterceptHandler(logging.Handler):
    """A stdlib logging handler that re-emits each record through loggerplusplus (loguru)."""

    def emit(self, record: logging.LogRecord) -> None:
        """
        Forward one stdlib log record into loggerplusplus, preserving level and origin.

        Args:
            record (logging.LogRecord): The record emitted by a stdlib logger (e.g. uvicorn).
        """
        # 1. Map the stdlib level to a loguru level name; fall back to the numeric level when the
        #    name is not one loguru knows (keeps an exotic custom level from crashing the handler).
        try:
            level: str | int = loggerplusplus.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 2. Walk back to the frame that actually issued the log so the source location points at the
        #    real caller (uvicorn), not this handler — matching loguru's documented intercept recipe.
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # 3. Re-emit through loggerplusplus with the original exception info; the global patcher then
        #    stamps the correlation id and the configured format renders it like any app log line.
        loggerplusplus.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


__all__ = ["LoggingInterceptHandler"]
