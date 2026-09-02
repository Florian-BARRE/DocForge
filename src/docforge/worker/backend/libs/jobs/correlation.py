# ====== Code Summary ======
# with_correlation — the worker-side mirror of the app's RequestIdMiddleware. It wraps an arq task so
# the correlation id passed by the enqueuing request (a plain `correlation_id` task kwarg — NOT a
# reserved arq control kwarg) is bound into the shared correlation ContextVar for the whole job, and
# thus stamped onto every log line the job emits. A job that arrives without one (a cron-triggered
# reap/GC) gets a freshly-minted id so worker logs are ALWAYS correlatable. The id is popped from
# kwargs so the wrapped task keeps its clean, id-free signature.

from __future__ import annotations

# ====== Standard Library Imports ======
import functools
from collections.abc import Awaitable, Callable
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.observability import CorrelationContext

# An arq task: `async def task(ctx, *args, **kwargs)`. Typed loosely — arq tasks vary in return type.
ArqTask = Callable[..., Awaitable[Any]]


def with_correlation(func: ArqTask) -> ArqTask:
    """
    Wrap an arq task so its whole execution runs under a bound correlation id.

    Args:
        func (ArqTask): The arq task coroutine (``async def task(ctx, ...)``).

    Returns:
        ArqTask: The wrapped task — same name/signature to arq (``functools.wraps`` preserves the
            ``__qualname__`` arq registers it under), with the correlation id bound for its duration.
    """

    @functools.wraps(func)
    async def wrapper(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        # 1. Take the enqueued id if present (a normal task kwarg), else mint one (cron jobs).
        correlation_id = kwargs.pop("correlation_id", None) or CorrelationContext.generate()

        # 2. Bind it for the whole job so every log line the task emits carries it.
        token = CorrelationContext.set(correlation_id)

        # 3. Run the task on its clean, id-free signature; always release the binding afterwards.
        try:
            return await func(ctx, *args, **kwargs)
        finally:
            CorrelationContext.reset(token)

    return wrapper


__all__ = ["with_correlation"]
