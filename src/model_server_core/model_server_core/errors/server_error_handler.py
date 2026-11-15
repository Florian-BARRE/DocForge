# ====== Code Summary ======
# ServerErrorHandler: the one place that turns an exception into an HTTP answer for a model-host
# micro-service. An unexpected exception becomes a TYPED JSON 500 carrying a generated correlation id
# and NEVER str(exc) or any internal detail; the full exception is logged with the SAME correlation
# id so the two can be matched. An InvalidInputError becomes a clean 422. Replaces the per-server
# `@auto_handle_errors` decorator, which returned `str(exc)` in the 500 body.

# ====== Standard Library Imports ======
from __future__ import annotations

import traceback
import uuid
from collections.abc import Callable
from typing import Final

# ====== Third-Party Library Imports ======
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .error_models import ErrorDetail, ErrorResponse
from .invalid_input_error import InvalidInputError

# ====== Constants ======
INTERNAL_ERROR_MESSAGE: Final[str] = "Internal server error. The details were logged."
CORRELATION_ID_HEADER: Final[str] = "X-Correlation-ID"


class ServerErrorHandler(LoggerClass):
    """Registers the exception handlers of a model server on its FastAPI app.

    Args:
        id_factory (Callable[[], str] | None): Source of correlation ids; a random UUID4 hex by
            default. Injectable so tests can pin the id.
    """

    # Private attributes
    _id_factory: Callable[[], str]

    def __init__(self, *, id_factory: Callable[[], str] | None = None) -> None:
        LoggerClass.__init__(self)
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)

    # =======================
    #   Private Methods
    # =======================
    async def _handle_unexpected(self, request: Request, exc: Exception) -> JSONResponse:
        """Answer an unexpected exception with a typed 500 and log it with the same id."""
        # 1. The correlation id ties the client-visible answer to the server-side log entry.
        correlation_id = self._id_factory()

        # 2. The full exception goes to the logs ONLY.
        trace = "".join(traceback.format_exception(exc))
        self.logger.error(
            f"Unhandled {type(exc).__name__} on {request.method} {request.url.path} "
            f"(correlation_id={correlation_id})\n{trace}"
        )

        # 3. The body is generic: no message, no type, no traceback of the exception.
        body = ErrorResponse(
            detail=ErrorDetail(error=INTERNAL_ERROR_MESSAGE, correlation_id=correlation_id)
        )
        return JSONResponse(
            status_code=500,
            content=body.model_dump(),
            headers={CORRELATION_ID_HEADER: correlation_id},
        )

    async def _handle_invalid_input(self, request: Request, exc: Exception) -> JSONResponse:
        """Answer an undecodable upload with a 422 carrying its (clean) message."""
        self.logger.warning(f"Invalid input on {request.method} {request.url.path}: {exc}")
        return JSONResponse(status_code=422, content={"detail": {"error": str(exc)}})

    # =======================
    #   Public Methods
    # =======================
    def install(self, app: FastAPI) -> None:
        """Register the handlers on `app`.

        `HTTPException` and request-validation errors keep FastAPI's own handlers, so a route that
        raises `HTTPException(413)` still answers 413.

        Args:
            app (FastAPI): The application to protect.
        """
        app.add_exception_handler(InvalidInputError, self._handle_invalid_input)
        app.add_exception_handler(Exception, self._handle_unexpected)
