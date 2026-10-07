# ====== Code Summary ======
# RedisProviderLimiter — the distributed counting semaphore behind the shared-embedder guard. Per
# endpoint, a Redis lease store (``RedisLeaseStore``) holds the live LEASES scored by their EXPIRY on the
# Redis server clock, plus a FIFO waiter queue; a caller is admitted only while fewer than ``limit``
# leases are live, oldest waiter first — so the cap holds across every worker process and replica, for
# any mix of lease lengths, and a crashed holder's lease simply expires (no manual cleanup).
#
# Release policy: a lease is given back on success and on an error raised BEFORE the request left
# (connect failure, pool timeout). When the guarded call dies AFTER its request was sent (client read/
# write timeout, mid-request transport error, cancellation), the provider is still computing the
# abandoned request — so the lease is KEPT until it expires (lease = request timeout + margin) instead
# of freeing a slot the server has not actually freed.
#
# Failure policy: Redis being unreachable FAILS OPEN (a warning, no slot) — the guard must never become a
# single point of failure for ingestion. A wait that exceeds the budget does NOT proceed: it raises
# ``ProviderSlotTimeout`` (a transient the embed retry/backoff handles) so the cap still holds under load.

# ====== Standard Library Imports ======
import asyncio
import random
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass
from redis.asyncio import Redis
from redis.exceptions import RedisError

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ProviderLimiter, ProviderSlotTimeout

# ====== Local Project Imports ======
from .lease_store import RedisLeaseStore

KEY_PREFIX = "docforge:embed:inflight:"

# Errors that certainly fired BEFORE the request reached the provider — nothing is running server-side.
_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.UnsupportedProtocol)
# Errors that may fire AFTER the request was sent — the provider may still be computing it.
_MAYBE_IN_FLIGHT = (httpx.TimeoutException, httpx.TransportError, asyncio.CancelledError)


class RedisProviderLimiter(ProviderLimiter, LoggerClass):
    """Redis lease semaphore: at most ``default_limit`` (or the call override) in-flight per endpoint."""

    def __init__(
        self,
        redis: Redis,
        default_limit: int,
        poll_seconds: float = 0.25,
        max_wait_seconds: float = 600.0,
    ) -> None:
        """
        Args:
            redis (Redis): The shared async Redis client (the arq broker's server).
            default_limit (int): The per-endpoint cap when a call passes none. Must be >= 1.
            poll_seconds (float): Base sleep between admission attempts (jittered).
            max_wait_seconds (float): Longest a caller waits for a slot before ``ProviderSlotTimeout``
                is raised (never proceeds without a slot — that would disable the cap under load).
        """
        LoggerClass.__init__(self)
        self._default_limit = default_limit
        self._poll = poll_seconds
        self._max_wait = max_wait_seconds
        # A live waiter polls every <= 1.5 x poll; 20 polls of silence (>= 5 s) means it is dead.
        self._store = RedisLeaseStore(redis, KEY_PREFIX, max(5.0, 20 * poll_seconds))

    async def __acquire(self, endpoint: str, token: str, limit: int, lease_seconds: float) -> None:
        """Queue ``token`` and poll until it holds a lease, or raise ``ProviderSlotTimeout``."""
        deadline = time.monotonic() + self._max_wait
        while True:
            # 1. Heartbeat (enqueue on the first pass), then one optimistic admission attempt.
            await self._store.heartbeat(endpoint, token)
            if await self._store.try_admit(endpoint, token, limit, lease_seconds):
                return
            # 2. Wait budget spent → a transient error, never a slot-less pass.
            if time.monotonic() >= deadline:
                await self._store.leave_queue(endpoint, token)
                raise ProviderSlotTimeout(
                    f"No embed slot on {endpoint} within {self._max_wait:.0f}s "
                    f"(cap {limit} in-flight saturated)"
                )
            await asyncio.sleep(self._poll * (0.5 + random.random()))

    async def __discard_quietly(self, endpoint: str, token: str) -> None:
        """Best-effort removal of every trace of ``token`` after an aborted acquisition."""
        try:
            await self._store.discard(endpoint, token)
        except Exception as error:  # noqa: BLE001 — the lease expires / the waiter goes stale anyway
            self.logger.warning(f"Embed slot cleanup failed ({error!r}); it will expire on its own")

    async def __take(self, endpoint: str, token: str, limit: int, lease_seconds: float) -> bool:
        """Acquire a lease → True; Redis unavailable → False (fail-open); anything else re-raised."""
        try:
            await self.__acquire(endpoint, token, limit, lease_seconds)
            return True
        except (RedisError, OSError) as error:
            self.logger.warning(
                f"Embed limiter unavailable ({error!r}) — proceeding without a slot"
            )
            await self.__discard_quietly(endpoint, token)
            return False
        except BaseException:
            # Cancellation can land after Redis applied our add but before we read the reply — drop
            # whatever we left (lease or waiter entry) so no ghost member pins capacity.
            await self.__discard_quietly(endpoint, token)
            raise

    @staticmethod
    def abandoned_in_flight(error: BaseException) -> bool:
        """Whether ``error`` may have left its request running on the provider (keep the lease)."""
        if isinstance(error, _NOT_SENT):
            return False
        return isinstance(error, _MAYBE_IN_FLIGHT)

    @asynccontextmanager
    async def slot(
        self, endpoint: str, *, max_inflight: int | None = None, lease_seconds: float = 60.0
    ) -> AsyncIterator[None]:
        """Wait for a free lease on ``endpoint``, hold it for the body, release it per the policy."""
        token = uuid.uuid4().hex
        held = await self.__take(
            endpoint, token, max_inflight or self._default_limit, lease_seconds
        )
        try:
            yield
        except BaseException as error:
            if held and self.abandoned_in_flight(error):
                # Keep the lease: the provider is still computing the abandoned request.
                held = False
                self.logger.warning(
                    f"Embed call on {endpoint} abandoned in flight ({error!r}) — its slot is held "
                    f"until the lease expires ({lease_seconds:.0f}s)"
                )
            raise
        finally:
            if held:
                try:
                    await self._store.release(endpoint, token)
                except Exception as error:  # noqa: BLE001 — expiry reclaims it anyway
                    self.logger.warning(f"Embed slot release failed ({error!r}); lease will expire")


__all__ = ["RedisProviderLimiter", "KEY_PREFIX"]
