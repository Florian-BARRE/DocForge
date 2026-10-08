# ====== Code Summary ======
# ResilientEmbedCalls — the retry + adaptive-split + limiter frame every embed provider call runs in.
# One call holds ONE in-flight slot on its endpoint (the shared Redis semaphore — a combined call is
# one slot); a transient error is retried with backoff, then the batch is halved and each half
# embedded independently. Shape-agnostic (a dense list, a sparse list, or the combined pair) and
# policy-driven: the caller hands the EmbedCallPolicy of the endpoint the call targets.
#
# Rules (unchanged from the single-provider embedder):
#   - max_retries counts retries BEYOND the first call (1 + max_retries attempts); 0 = one shot, no
#     retry and no split.
#   - timeout-splits-sooner: a client TIMEOUT on a multi-text batch splits after ONE attempt (retrying
#     the same oversized batch only stacks load on a saturated CPU embedder).
#   - a ProviderSlotTimeout (no limiter slot) and a 429/503 overload are retried but NEVER split.

# ====== Standard Library Imports ======
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import EndpointKey, ProviderLimiterRegistry, ProviderSlotTimeout

# ====== Local Project Imports ======
from .policy import EmbedCallPolicy

# The longest provider Retry-After honoured before a retry (a misbehaving header must never park a
# job for minutes; the retry budget then decides).
_RETRY_AFTER_CAP_SECONDS = 30.0
# Extra lease time over the request timeout: an abandoned request keeps its slot about as long as the
# provider may still be computing it, and a crashed holder frees itself.
_LEASE_MARGIN_SECONDS = 15.0
_TRANSIENT_STATUSES = (429, 500, 502, 503, 504)

_Batch = TypeVar("_Batch")


class ResilientEmbedCalls:
    """Mixin: the policy-driven retry/split/limiter frame around one embed provider hook."""

    logger: Any
    KIND: str

    @staticmethod
    def __is_overload(error: Exception) -> bool:
        """The provider said "busy, come back later" (429 / 503): wait, never split the batch."""
        return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (429, 503)

    @staticmethod
    def __retry_after(error: Exception) -> float | None:
        """The provider's ``Retry-After`` delay in seconds (delta form only), capped; else None."""
        if not isinstance(error, httpx.HTTPStatusError):
            return None
        try:
            delay = float(error.response.headers.get("Retry-After", ""))
        except ValueError:
            return None
        return min(max(delay, 0.0), _RETRY_AFTER_CAP_SECONDS)

    @staticmethod
    def __is_transient(error: Exception) -> bool:
        """A timeout, a transport blip, a 429/5xx, or no limiter slot in time — worth retrying."""
        if isinstance(error, httpx.TimeoutException | httpx.TransportError | ProviderSlotTimeout):
            return True
        return (
            isinstance(error, httpx.HTTPStatusError)
            and error.response.status_code in _TRANSIENT_STATUSES
        )

    async def _limited(
        self,
        embed_fn: Callable[[list[str]], Awaitable[_Batch | None]],
        texts: list[str],
        policy: EmbedCallPolicy,
    ) -> _Batch | None:
        """Run ONE provider call while holding an in-flight slot on the policy's endpoint.

        The slot wraps only the wire call, never the backoff sleep. An in-process encoder (no
        endpoint) has no remote capacity to protect and runs directly. Unbound (tests, search) the
        registry yields the no-op limiter. Raises ``ProviderSlotTimeout`` when no slot frees in time.
        """
        if not policy.endpoint:
            return await embed_fn(texts)
        async with ProviderLimiterRegistry.current().slot(
            EndpointKey.normalize(policy.endpoint),
            max_inflight=policy.max_concurrency,
            lease_seconds=policy.timeout_seconds + _LEASE_MARGIN_SECONDS,
        ):
            return await embed_fn(texts)

    async def _resilient(
        self,
        embed_fn: Callable[[list[str]], Awaitable[_Batch | None]],
        texts: list[str],
        concat: Callable[[_Batch, _Batch], _Batch],
        policy: EmbedCallPolicy,
    ) -> _Batch | None:
        """
        Call one provider hook with backoff-retry, then adaptive batch splitting (see module rules).

        Args:
            embed_fn (Callable): The provider hook (one batch in, aligned outputs out).
            texts (list[str]): The batch.
            concat (Callable): Joins two halves' outputs in order.
            policy (EmbedCallPolicy): The endpoint's retry/limiter policy.

        Returns:
            The aligned outputs, or None when the hook reports the route unsupported.
        """
        if policy.max_retries == 0:
            return await self._limited(embed_fn, texts, policy)
        total_attempts = 1 + policy.max_retries
        last_error: Exception | None = None
        for attempt in range(1, total_attempts + 1):
            try:
                return await self._limited(embed_fn, texts, policy)
            except Exception as error:  # noqa: BLE001 — re-raised below unless transient
                if not self.__is_transient(error):
                    raise
                last_error = error
                split_on_timeout = isinstance(error, httpx.TimeoutException) and len(texts) > 1
                self.logger.warning(
                    f"Embedder '{self.KIND}' transient error on a {len(texts)}-text batch "
                    f"(attempt {attempt}/{total_attempts}"
                    f"{'; splitting now — timeout on a multi-text batch' if split_on_timeout else ''})"
                    f": {error!r}"
                )
                if split_on_timeout:
                    break
                if attempt < total_attempts:
                    backoff = policy.retry_backoff_seconds * attempt
                    await asyncio.sleep(max(backoff, self.__retry_after(error) or 0.0))
        # Retries exhausted (``last_error`` is always set here) — split, or surface the genuine error.
        if (
            len(texts) <= 1
            or isinstance(last_error, ProviderSlotTimeout)
            or self.__is_overload(last_error)  # type: ignore[arg-type]
        ):
            raise last_error  # type: ignore[misc]
        mid = len(texts) // 2
        self.logger.warning(
            f"Embedder '{self.KIND}' still failing a {len(texts)}-text batch — splitting to "
            f"{mid} + {len(texts) - mid} and retrying each half"
        )
        left = await self._resilient(embed_fn, texts[:mid], concat, policy)
        right = await self._resilient(embed_fn, texts[mid:], concat, policy)
        if left is None or right is None:
            return None
        return concat(left, right)


__all__ = ["ResilientEmbedCalls"]
