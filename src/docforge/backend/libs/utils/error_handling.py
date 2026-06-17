# ====== Code Summary ======
# @auto_handle_errors decorator: wraps all route functions to catch unexpected exceptions,
# log them with full traceback, and return HTTP 500.  Traceback included in response only
# when FASTAPI_DEBUG_MODE is True (never in production).

# ====== Standard Library Imports ======
import functools
import inspect
import traceback
from typing import Any, Callable

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT


def _build_error_detail(func_name: str, exc: Exception, tb: str) -> dict[str, Any]:
    """
    Build the HTTP 500 response detail dict.

    In debug mode: includes function name, error message, and full traceback.
    In production: returns only a generic error message (no internal info leaked).

    Args:
        func_name (str): Name of the failing route function.
        exc (Exception): The caught exception.
        tb (str): Formatted traceback string.

    Returns:
        dict: Error detail dictionary for the HTTPException response body.
    """
    if getattr(CONTEXT.RUNTIME_CONFIG, "FASTAPI_DEBUG_MODE", False):
        return {
            "error": str(exc),
            "traceback": tb,
            "function": func_name,
        }
    return {"error": "Internal server error."}


def auto_handle_errors(func: Callable) -> Callable:
    """
    Decorator that automatically handles unexpected exceptions in route functions.

    - Supports both sync and async route functions.
    - Re-raises ``HTTPException`` as-is (these are intentional error responses).
    - Catches all other exceptions, logs them with traceback, and raises HTTP 500.

    Usage::
        @router.get("/my-route")
        @auto_handle_errors
        async def my_route() -> MyResponse:
            ...

    Args:
        func (Callable): The route function to wrap.

    Returns:
        Callable: Wrapped function with automatic error handling.
    """

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(
                status_code=500,
                detail=_build_error_detail(func.__name__, exc, tb),
            )

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(
                status_code=500,
                detail=_build_error_detail(func.__name__, exc, tb),
            )

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
