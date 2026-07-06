# ====== Code Summary ======
# This module defines the `auto_handle_errors` decorator, which wraps synchronous or asynchronous functions
# to automatically handle unexpected exceptions. If an unhandled exception occurs (other than HTTPException),
# it logs the error, formats the traceback, and raises a FastAPI HTTPException with status 500,
# including details about the error, traceback, and function name. This helps centralize error handling and
# ensures that exceptions are properly reported to both logs and API clients.

# ====== Standard Library Imports ======
import functools
import inspect
import traceback

# ====== Third-party Library Imports ======
from fastapi import HTTPException

# ====== Local Project Imports ======
from ..context import CONTEXT


def auto_handle_errors(func):
    """
    Decorator to automatically handle unexpected exceptions for both sync and async functions.
    It logs the error with traceback and raises an HTTPException with status code 500 if
    a non-HTTPException occurs.

    Args:
        func (Callable): The function to wrap, can be synchronous or asynchronous.

    Returns:
        Callable: The wrapped function with automatic error handling.
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
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
            # If any other exception occurs, capture traceback and log error with context
            tb = traceback.format_exc()
            detail = {
                "error": str(exc),
                "traceback": tb,
                "function": func.__name__,
            }
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            # Raise as HTTPException with status code 500 and detailed information
            raise HTTPException(status_code=500, detail=detail)

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
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
            # If any other exception occurs, capture traceback and log error with context
            tb = traceback.format_exc()
            detail = {
                "error": str(exc),
                "traceback": tb,
                "function": func.__name__,
            }
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            # Raise as HTTPException with status code 500 and detailed information
            raise HTTPException(status_code=500, detail=detail)

    # Check if the wrapped function is asynchronous (coroutine), and return appropriate wrapper
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper