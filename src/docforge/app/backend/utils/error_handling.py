# ====== Code Summary ======
# This module defines the `auto_handle_errors` decorator, which wraps synchronous or asynchronous functions
# to automatically handle unexpected exceptions. If an unhandled exception occurs (other than HTTPException),
# it logs the full error and traceback server-side and raises a FastAPI HTTPException with status 500.
# The client-facing `detail` is a generic message by default and only carries the error/traceback/function
# breakdown when FASTAPI_DEBUG_MODE is enabled — a stack trace is never leaked to clients in production.

# ====== Standard Library Imports ======
import functools
import inspect
import traceback
from collections.abc import Callable
from typing import Any

# ====== Third-party Library Imports ======
from fastapi import HTTPException

# ====== Local Project Imports ======
from ..context import CONTEXT

# The opaque detail returned to clients when debug mode is off — never a stack trace.
_GENERIC_DETAIL = "Internal server error"


def _error_detail(exc: Exception, function_name: str, tb: str) -> Any:
    """
    Build the client-facing 500 detail, gated on debug mode.

    Args:
        exc (Exception): The unhandled exception.
        function_name (str): The wrapped function's name.
        tb (str): The formatted traceback (already logged server-side).

    Returns:
        Any: The verbose {error, traceback, function} breakdown when FASTAPI_DEBUG_MODE is
        enabled, otherwise a generic opaque string.
    """
    # 1. Only surface internals when the app is explicitly running in debug mode.
    if CONTEXT.RUNTIME_CONFIG.FASTAPI_DEBUG_MODE:
        return {"error": str(exc), "traceback": tb, "function": function_name}
    # 2. Production default — leak nothing about the failure to the caller.
    return _GENERIC_DETAIL


def auto_handle_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to automatically handle unexpected exceptions for both sync and async functions.
    It logs the error with traceback and raises an HTTPException with status code 500 if
    a non-HTTPException occurs.

    Args:
        func (Callable[..., Any]): The function to wrap, can be synchronous or asynchronous.

    Returns:
        Callable[..., Any]: The wrapped function with automatic error handling.
    """

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Wrapper for asynchronous functions to handle errors.

        Args:
            *args: Positional arguments for the original function.
            **kwargs: Keyword arguments for the original function.

        Returns:
            Any: Result from the original async function.

        Raises:
            HTTPException: Re-raises FastAPI HTTPException or wraps other exceptions.
        """
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Preserve HTTPException, re-raise so FastAPI handles as intended
            raise
        except Exception as exc:
            # Capture + log the full traceback server-side; the client detail is gated on debug mode.
            tb = traceback.format_exc()
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(status_code=500, detail=_error_detail(exc, func.__name__, tb))

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Wrapper for synchronous functions to handle errors.

        Args:
            *args: Positional arguments for the original function.
            **kwargs: Keyword arguments for the original function.

        Returns:
            Any: Result from the original sync function.

        Raises:
            HTTPException: Re-raises FastAPI HTTPException or wraps other exceptions.
        """
        try:
            return func(*args, **kwargs)
        except HTTPException:
            # Preserve HTTPException, re-raise so FastAPI handles as intended
            raise
        except Exception as exc:
            # Capture + log the full traceback server-side; the client detail is gated on debug mode.
            tb = traceback.format_exc()
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(status_code=500, detail=_error_detail(exc, func.__name__, tb))

    # Check if the wrapped function is asynchronous (coroutine), and return appropriate wrapper
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


__all__ = ["auto_handle_errors"]
