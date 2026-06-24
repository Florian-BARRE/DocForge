# ====== Code Summary ======
# Provides the @auto_handle_errors decorator for automatic exception handling on all routes.
# Catches any non-HTTPException, logs it with a full traceback, and returns HTTP 500. The full
# traceback goes to the LOGS ONLY; the response body is always the generic {"error": str(exc)}
# so internal details are never exposed to callers. This is a simplification of the fastapi.md
# pattern: the BGE micro-service is an internal model-host with no FASTAPI_DEBUG_MODE toggle, so
# there is no debug branch that would surface the traceback in the body.

# ====== Standard Library Imports ======
import functools
import inspect
import traceback

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

logger = loggerplusplus.bind(identifier="ErrorHandler")


def auto_handle_errors(func):
    """
    Decorator to automatically handle unexpected exceptions for sync and async route functions.

    Logs the error with full traceback and raises an HTTPException (500).
    HTTPExceptions are always re-raised as-is.

    Args:
        func (Callable): The route function to wrap.

    Returns:
        Callable: Wrapped function with automatic error handling.
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc)},
            )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc)},
            )

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
