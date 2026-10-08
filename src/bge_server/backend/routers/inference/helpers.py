# ====== Code Summary ======
# Static helpers for the inference router. Provides input normalization shared by the
# /embed and /embed_sparse routes. Per-request tracing logs live in router.py (bound to
# "InferenceRouter") where the batch size is known; no logger is needed here.


# ====== Standard Library Imports ======
import asyncio
from collections.abc import Awaitable
from typing import TypeVar

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request

_T = TypeVar("_T")


class ClientDisconnected(Exception):
    """Raised when the HTTP client went away before its request finished (work dropped)."""


class InferenceHelpers:
    """
    Static utility helpers for the BGE inference router.

    Handles input normalization shared across the /embed and /embed_sparse routes.
    Per-request tracing is done in router.py where the full request context is available.
    """

    # `-> None` is the project's static-only guard idiom (python.md); mypy's [misc] "must return an
    # instance" is a false positive here, and `-> NoReturn` would make mypy treat the class as Never
    # and lose its @staticmethods — so suppress just this check.
    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError(f"InferenceHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def as_list(inputs: list[str] | str) -> list[str]:
        """
        Normalize the TEI ``inputs`` field (str or list[str]) into a plain list of texts.

        TEI accepts either a single string or a batch list — both must produce identical
        downstream behaviour. This normalization step ensures the model service always
        receives a list.

        Args:
            inputs (list[str] | str): Raw ``inputs`` value from the request body.

        Returns:
            list[str]: A list containing the input text(s).
        """
        return [inputs] if isinstance(inputs, str) else list(inputs)

    @staticmethod
    def overloaded(retry_after_seconds: int) -> HTTPException:
        """
        Build the 503 returned when the bounded wait queue cannot take another request.

        Args:
            retry_after_seconds (int): Value of the Retry-After header.

        Returns:
            HTTPException: 503 with a Retry-After header.
        """
        return HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": str(retry_after_seconds)},
        )

    @staticmethod
    async def await_unless_disconnected(
        request: Request, awaitable: Awaitable[_T], poll_seconds: float
    ) -> _T:
        """
        Await an engine call, abandoning it as soon as the client disconnects.

        The engine call runs as a task; while it is pending the client connection is polled.
        On disconnect the task is cancelled, which cancels the request's future: a queued item
        is then dropped by the worker without running, and a running batch stops at the next
        sub-batch boundary (a forward pass already inside its thread cannot be interrupted).

        Args:
            request (Request): The incoming request, polled with ``is_disconnected()``.
            awaitable (Awaitable): The engine call to run.
            poll_seconds (float): Seconds between disconnect polls.

        Returns:
            The awaited call's result.

        Raises:
            ClientDisconnected: When the client is gone (before or during the call).
        """
        # 1. Never start work for a client that is already gone
        if await request.is_disconnected():
            close = getattr(awaitable, "close", None)
            if close is not None:
                close()  # un-awaited coroutine would warn otherwise
            raise ClientDisconnected()

        # 2. Run the call, polling the connection until it finishes
        task = asyncio.ensure_future(awaitable)
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=poll_seconds)
                if done:
                    return task.result()
                if await request.is_disconnected():
                    raise ClientDisconnected()
        finally:
            # Covers disconnect AND the handler itself being cancelled by the server
            if not task.done():
                task.cancel()
