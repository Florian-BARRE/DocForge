# ====== Code Summary ======
# IdempotencyApi — the data-access API for the Stripe-style `idempotency_key` table. It backs the
# app's idempotency middleware: INSERT one in-progress record (the concurrency-guard write — the
# UNIQUE constraint makes the loser of a concurrent race raise), SELECT it back for the replay/reuse
# decision, UPDATE it to completed with the cached response, DELETE it (so a failed handler can be
# retried), and age-prune expired rows (the worker GC cron). Postgres-only, session-driven — the
# IdempotencyFacade composes it and owns the unique-violation → conflict translation.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import IdempotencyKey, IdempotencyState


class IdempotencyApi:
    """Static data-access API for the idempotency-key store (guard INSERT + cache lifecycle)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IdempotencyApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def insert_in_progress(
        session: AsyncSession,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
        request_fingerprint: str,
        expires_at: datetime,
    ) -> IdempotencyKey:
        """
        Insert one in-progress record and flush it (so the UNIQUE guard fires here, not on commit).

        The flush is deliberate: it forces the INSERT to hit Postgres inside this call so a concurrent
        first-request that already holds the row raises the UniqueViolation NOW (which the façade
        catches and turns into a conflict), rather than on the context manager's later commit.

        Args:
            session (AsyncSession): The active session.
            actor_scope (str): The resolved actor identity ("key:<uuid>"/"user:<uuid>"/"anon").
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE (never a raw-id path).
            idempotency_key (str): The client-supplied ``Idempotency-Key`` header value.
            request_fingerprint (str): sha256 hex of the request body.
            expires_at (datetime): The TTL horizon past which the GC cron deletes this row.

        Returns:
            IdempotencyKey: The persisted in-progress row (state defaults to ``in_progress``).
        """
        # 1. Build the in-progress row — id (BIGINT IDENTITY) + created_at (server default) are
        #    DB-generated; state defaults to in_progress; the response columns stay NULL until complete.
        row = IdempotencyKey(
            actor_scope=actor_scope,
            method=method,
            path=path,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            expires_at=expires_at,
        )
        # 2. Add + flush so the UNIQUE constraint is evaluated within this call (the concurrency guard).
        session.add(row)
        await session.flush()
        return row

    @staticmethod
    async def get(
        session: AsyncSession,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
    ) -> IdempotencyKey | None:
        """
        Load the single record for one (actor, method, route template, client key), if it exists.

        Args:
            session (AsyncSession): The active session.
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.

        Returns:
            IdempotencyKey | None: The matching row, or None when no record exists yet.
        """
        # 1. One point lookup on the UNIQUE key columns.
        query = select(IdempotencyKey).where(
            IdempotencyKey.actor_scope == actor_scope,
            IdempotencyKey.method == method,
            IdempotencyKey.path == path,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def complete(
        session: AsyncSession,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
        response_status: int,
        response_body: bytes,
        response_media_type: str | None,
        completed_at: datetime,
    ) -> None:
        """
        Transition the in-progress record to completed, caching the response for verbatim replay.

        Args:
            session (AsyncSession): The active session.
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.
            response_status (int): The buffered response status code (a definitive < 500).
            response_body (bytes): The buffered response body bytes (cached byte-exact).
            response_media_type (str | None): The buffered response content-type, if any.
            completed_at (datetime): The instant the handler finished.
        """
        # 1. One UPDATE keyed on the UNIQUE columns — flip state + fill the cached response.
        statement = (
            update(IdempotencyKey)
            .where(
                IdempotencyKey.actor_scope == actor_scope,
                IdempotencyKey.method == method,
                IdempotencyKey.path == path,
                IdempotencyKey.idempotency_key == idempotency_key,
            )
            .values(
                state=IdempotencyState.completed,
                response_status=response_status,
                response_body=response_body,
                response_media_type=response_media_type,
                completed_at=completed_at,
            )
        )
        await session.execute(statement)

    @staticmethod
    async def delete(
        session: AsyncSession,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
    ) -> None:
        """
        Delete the record for one (actor, method, route template, client key).

        Called when the handler raised or returned a 5xx: dropping the in-progress row lets a retry
        carrying the same key re-run the handler (only successful/definitive outcomes are replayable).

        Args:
            session (AsyncSession): The active session.
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.
        """
        # 1. One point delete on the UNIQUE key columns.
        statement = delete(IdempotencyKey).where(
            IdempotencyKey.actor_scope == actor_scope,
            IdempotencyKey.method == method,
            IdempotencyKey.path == path,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
        await session.execute(statement)

    @staticmethod
    async def prune(session: AsyncSession, cutoff: datetime) -> int:
        """
        Delete every record whose ``expires_at`` is strictly before ``cutoff`` and return the count.

        Args:
            session (AsyncSession): The active session.
            cutoff (datetime): Rows with ``expires_at`` before this are removed (the GC "now").

        Returns:
            int: The number of rows deleted.
        """
        # 1. Age-based bulk delete — the ix_idempotency_key_expires_at btree bounds the scan.
        result = await session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.expires_at < cutoff)
        )
        return result.rowcount or 0


__all__ = ["IdempotencyApi"]
