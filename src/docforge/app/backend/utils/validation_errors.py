# ====== Code Summary ======
# The request-validation (422) handler. FastAPI's default handler echoes every error's `input` — the
# offending value, or for a missing field the WHOLE request body — so a malformed request carrying a
# provider api_key, a password or document text gets it reflected straight back (and into any proxy,
# client or log that records error bodies). This handler answers the same `{"detail": [...]}` shape
# with each error's `type`, `loc`, `msg` and `ctx`, but never its `input`.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# The keys of one pydantic error kept in the response — everything except the raw `input` (and the
# docs `url`, noise for an API client).
_KEPT_KEYS = ("type", "loc", "msg", "ctx")


class ValidationErrorHandler:
    """Static installer of the input-free 422 handler."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ValidationErrorHandler is a static-only class and cannot be instantiated.")

    @staticmethod
    def _scrub(errors: list[dict]) -> list[dict]:
        """Keep only the safe keys of each error (never the submitted value)."""
        return [{key: error[key] for key in _KEPT_KEYS if key in error} for error in errors]

    @classmethod
    async def _handle(cls, request: Request, exc: RequestValidationError) -> JSONResponse:
        """Answer a request-validation failure as 422 without echoing what was submitted."""
        # 1. Encode the context values (exceptions, enums) the way FastAPI's default handler does,
        #    then drop every `input`.
        return JSONResponse(
            status_code=422, content={"detail": jsonable_encoder(cls._scrub(exc.errors()))}
        )

    @classmethod
    def install(cls, app: FastAPI) -> None:
        """
        Register the handler on ``app`` (replaces FastAPI's default RequestValidationError handler).

        Args:
            app (FastAPI): The application.
        """
        app.add_exception_handler(RequestValidationError, cls._handle)


__all__ = ["ValidationErrorHandler"]
