# ====== Code Summary ======
# RedisLeaseStore — the Redis data model of one endpoint's in-flight semaphore. Three keys per endpoint:
#   • ``<prefix><endpoint>``          holders — member = a lease token, score = its EXPIRY (server clock).
#   • ``<prefix><endpoint>:queue``    waiters — member = a waiting token, score = its FIRST arrival.
#   • ``<prefix><endpoint>:seen``     waiter heartbeats — score = the waiter's last poll.
# Every timestamp is the Redis server's ``TIME`` (never a worker's local clock, which may be skewed). A
# lease is live while its expiry is in the future, whatever lease length its holder chose, so a caller
# with a short lease can never evict a longer holder. Admission is an optimistic WATCH/MULTI transaction:
# a waiter is admitted only when it ranks among the ``limit - live`` oldest LIVE waiters (FIFO — a
# waiter that stops heart-beating is skipped, then purged) and nobody touched the HOLDERS between the
# read and the write (only the holders are watched: the cap lives there, while the queue — refreshed by
# every waiter's heartbeat — only orders admission). A lost race simply retries on the next poll, so
# the cap is never over-admitted.

# ====== Third-Party Library Imports ======
from redis.asyncio import Redis
from redis.exceptions import WatchError

# Extra seconds the holders key outlives its longest live lease (crash-safe key garbage collection).
_KEY_TTL_MARGIN_SECONDS = 60.0


class RedisLeaseStore:
    """Holders/queue/heartbeat sorted sets of one Redis server, keyed per endpoint."""

    def __init__(self, redis: Redis, key_prefix: str, waiter_stale_seconds: float) -> None:
        """
        Args:
            redis (Redis): The shared async Redis client.
            key_prefix (str): Prefix of every key (the endpoint identity is appended).
            waiter_stale_seconds (float): A waiter not seen polling for this long is presumed dead
                (crashed worker) — skipped at admission and purged.
        """
        self._redis = redis
        self._prefix = key_prefix
        self._stale = waiter_stale_seconds

    def __holders_key(self, endpoint: str) -> str:
        """The holders key (score = lease expiry)."""
        return f"{self._prefix}{endpoint}"

    def __queue_key(self, endpoint: str) -> str:
        """The FIFO waiter key (score = first arrival)."""
        return f"{self._prefix}{endpoint}:queue"

    def __seen_key(self, endpoint: str) -> str:
        """The waiter-heartbeat key (score = last poll)."""
        return f"{self._prefix}{endpoint}:seen"

    @staticmethod
    def __text(member: bytes | str) -> str:
        """A sorted-set member as text (the client may return bytes)."""
        return member.decode() if isinstance(member, bytes) else member

    @staticmethod
    def server_now(time_reply: tuple[int, int]) -> float:
        """Convert a Redis ``TIME`` reply (seconds, microseconds) to float epoch seconds."""
        seconds, micros = time_reply
        return int(seconds) + int(micros) / 1_000_000

    async def heartbeat(self, endpoint: str, token: str) -> None:
        """Enqueue ``token`` (first arrival keeps its place) and refresh its liveness stamp."""
        # 1. The server clock stamps both the arrival (NX: kept across polls) and the heartbeat.
        now = self.server_now(await self._redis.time())
        queue, seen = self.__queue_key(endpoint), self.__seen_key(endpoint)
        ttl = max(1, int(self._stale * 4))
        # 2. One MULTI: a waiter is never half-registered (queued without a heartbeat or vice versa).
        pipe = self._redis.pipeline(transaction=True)
        pipe.zadd(queue, {token: now}, nx=True)
        pipe.zadd(seen, {token: now})
        pipe.expire(queue, ttl)
        pipe.expire(seen, ttl)
        await pipe.execute()

    async def try_admit(self, endpoint: str, token: str, limit: int, lease_seconds: float) -> bool:
        """
        One optimistic admission attempt for a queued ``token``.

        Returns:
            bool: True when the token now holds a lease (expiry = server now + ``lease_seconds``);
                False when the endpoint is full, the token is not yet at the head, or a concurrent
                admission won the race (the caller simply polls again).
        """
        holders, queue, seen = (
            self.__holders_key(endpoint),
            self.__queue_key(endpoint),
            self.__seen_key(endpoint),
        )
        async with self._redis.pipeline(transaction=True) as pipe:
            try:
                # 1. Snapshot under WATCH: live holders, live waiters in FIFO order, the server clock.
                await pipe.watch(holders)
                now = self.server_now(await pipe.time())
                live = await pipe.zcount(holders, now, "+inf")
                stale = {
                    self.__text(member)
                    for member in await pipe.zrangebyscore(seen, "-inf", now - self._stale)
                }
                waiting = [self.__text(member) for member in await pipe.zrange(queue, 0, -1)]
                alive = [member for member in waiting if member not in stale]
                # 2. Admit only within the free capacity, oldest live waiter first.
                if token not in alive or alive.index(token) >= limit - live:
                    await pipe.unwatch()
                    return False
                longest = await pipe.zrange(holders, -1, -1, withscores=True)
                expiry = now + lease_seconds
                key_expiry = max([expiry, *(score for _, score in longest)])
                # 3. Commit: purge expired leases + dead waiters, move the token queue → holders.
                pipe.multi()
                pipe.zremrangebyscore(holders, "-inf", f"({now}")
                pipe.zadd(holders, {token: expiry})
                pipe.expire(holders, int(key_expiry - now + _KEY_TTL_MARGIN_SECONDS))
                pipe.zrem(queue, token, *stale)
                pipe.zrem(seen, token, *stale)
                await pipe.execute()
                return True
            except WatchError:
                return False

    async def release(self, endpoint: str, token: str) -> None:
        """Give ``token``'s lease back immediately."""
        await self._redis.zrem(self.__holders_key(endpoint), token)

    async def discard(self, endpoint: str, token: str) -> None:
        """Remove every trace of ``token`` (lease and waiter entries) — the abort cleanup."""
        pipe = self._redis.pipeline(transaction=True)
        pipe.zrem(self.__holders_key(endpoint), token)
        pipe.zrem(self.__queue_key(endpoint), token)
        pipe.zrem(self.__seen_key(endpoint), token)
        await pipe.execute()

    async def leave_queue(self, endpoint: str, token: str) -> None:
        """Withdraw a waiter that gives up (wait budget spent) without touching any lease."""
        pipe = self._redis.pipeline(transaction=True)
        pipe.zrem(self.__queue_key(endpoint), token)
        pipe.zrem(self.__seen_key(endpoint), token)
        await pipe.execute()


__all__ = ["RedisLeaseStore"]
