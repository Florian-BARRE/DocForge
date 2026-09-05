# ====== Code Summary ======
# IdempotencyFacade — the data-layer gateway for the Stripe-style idempotency store. The app's
# idempotency middleware calls `begin(...)` (the guard INSERT: it either wins the race and gets a
# fresh in-progress record, or catches the UNIQUE violation and returns the existing row so the
# middleware can replay / 409 / 422), then `complete(...)` to cache a definitive response or
# `delete(...)` to drop a failed one so a retry re-runs; the worker GC cron calls `prune(now)` to age
# out expired rows. Postgres-only. This façade OWNS the one non-obvious rule: translating the UNIQUE
# constraint violation (uq_idempotency_key_scope) into a "someone else got there first" signal.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import IdempotencyApi

# ====== Local Project Imports ======
from .idempotency_payloads import IdempotencyBegin, IdempotencyRecord

# The UNIQUE constraint that guards concurrency — must match the name declared on the IdempotencyKey
# table (uq_idempotency_key_scope). asyncpg exposes the violated constraint name on its native error;
# under SQLAlchemy's asyncpg adapter that native error is the wrapper's ``__cause__`` (the adapter's
# own ``error.orig`` carries no ``constraint_name``), so both hops are inspected. Matching the name
# lets the façade tell "another request already holds this key" apart from any other integrity failure.
_SCOPE_CONSTRAINT = "uq_idempotency_key_scope"


class IdempotencyFacade(LoggerClass):
    """Guard-insert, complete, drop, read, and prune Stripe-style idempotency records."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth store.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

    @staticmethod
    def _is_scope_conflict(error: IntegrityError) -> bool:
        """
        Decide whether an IntegrityError is the idempotency UNIQUE-guard violation (a lost race).

        Args:
            error (IntegrityError): The error raised by the guard INSERT's flush.

        Returns:
            bool: True only when the violated constraint is ``uq_idempotency_key_scope``.
        """
        # 1. Walk the driver error and its __cause__ (the SQLAlchemy asyncpg adapter nests the native
        #    asyncpg error, which is the one carrying constraint_name) and match the guard's name.
        #    Matching the name is precise (this table has exactly one UNIQUE constraint) and avoids
        #    treating an unrelated integrity failure as a benign conflict.
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == _SCOPE_CONSTRAINT
            for candidate in candidates
        )

    async def begin(
        self,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
        request_fingerprint: str,
        expires_at: datetime,
    ) -> IdempotencyBegin:
        """
        Attempt the guard INSERT; on a lost race, return the existing record instead of raising.

        Args:
            actor_scope (str): The resolved actor identity ("key:<uuid>"/"user:<uuid>"/"anon").
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied ``Idempotency-Key`` header value.
            request_fingerprint (str): sha256 hex of the request body.
            expires_at (datetime): The TTL horizon for this record.

        Returns:
            IdempotencyBegin: ``created=True`` + the fresh in-progress snapshot when this request won
                the INSERT; ``created=False`` + the existing row's snapshot when another request
                already holds the key (the middleware then replays / 409 / 422).
        """
        # 1. One session: try the guard INSERT; a UNIQUE violation means a concurrent (or prior)
        #    request already owns this (actor, method, path, key) — catch it, rollback, and read the
        #    incumbent row back so the middleware can decide replay vs conflict.
        async with self._postgres.session() as session:
            try:
                row = await IdempotencyApi.insert_in_progress(
                    session,
                    actor_scope=actor_scope,
                    method=method,
                    path=path,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    expires_at=expires_at,
                )
                return IdempotencyBegin(created=True, record=IdempotencyRecord.from_row(row))
            except IntegrityError as error:
                # 2. Re-raise anything that is NOT our concurrency guard — a real, unexpected failure.
                if not self._is_scope_conflict(error):
                    raise
                # 3. The lost-race path: reset the aborted transaction, then read the incumbent row.
                await session.rollback()
                existing = await IdempotencyApi.get(
                    session,
                    actor_scope=actor_scope,
                    method=method,
                    path=path,
                    idempotency_key=idempotency_key,
                )
                record = IdempotencyRecord.from_row(existing) if existing is not None else None
                return IdempotencyBegin(created=False, record=record)

    async def complete(
        self,
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
        Cache a definitive response on the record so retries replay it (state → completed).

        Args:
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.
            response_status (int): The definitive (< 500) response status.
            response_body (bytes): The buffered response body bytes.
            response_media_type (str | None): The buffered response content-type.
            completed_at (datetime): The instant the handler finished.
        """
        # 1. One committed UPDATE flipping the record to completed with its cached response.
        async with self._postgres.session() as session:
            await IdempotencyApi.complete(
                session,
                actor_scope=actor_scope,
                method=method,
                path=path,
                idempotency_key=idempotency_key,
                response_status=response_status,
                response_body=response_body,
                response_media_type=response_media_type,
                completed_at=completed_at,
            )

    async def reclaim_stale(
        self,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
        request_fingerprint: str,
        expires_at: datetime,
        claimed_at: datetime,
        stale_before: datetime,
    ) -> bool:
        """
        Atomically re-claim a STALE in-progress record (crashed owner) onto the retrying request.

        Args:
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.
            request_fingerprint (str): sha256 hex of the reclaiming request's body.
            expires_at (datetime): The fresh TTL horizon for the reclaimed record.
            claimed_at (datetime): The reclaim instant — the record's new in-progress start clock.
            stale_before (datetime): Only a record whose ``created_at`` predates this is reclaimable.

        Returns:
            bool: True only when THIS call won the atomic claim (the middleware then runs the handler);
                False when the record was NOT stale, already gone, or a concurrent retry won the race.
        """
        # 1. One committed conditional UPDATE — the API owns the mutual-exclusion semantics.
        async with self._postgres.session() as session:
            return await IdempotencyApi.reclaim_stale(
                session,
                actor_scope=actor_scope,
                method=method,
                path=path,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                expires_at=expires_at,
                claimed_at=claimed_at,
                stale_before=stale_before,
            )

    async def delete(
        self,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
    ) -> None:
        """
        Drop the in-progress record so a retry with the same key re-runs the handler.

        Args:
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.
        """
        # 1. One committed DELETE on the UNIQUE key columns.
        async with self._postgres.session() as session:
            await IdempotencyApi.delete(
                session,
                actor_scope=actor_scope,
                method=method,
                path=path,
                idempotency_key=idempotency_key,
            )

    async def get(
        self,
        *,
        actor_scope: str,
        method: str,
        path: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        """
        Return the record snapshot for one (actor, method, route template, key), if it exists.

        Args:
            actor_scope (str): The resolved actor identity.
            method (str): The request's HTTP method.
            path (str): The eligible route TEMPLATE.
            idempotency_key (str): The client-supplied key.

        Returns:
            IdempotencyRecord | None: The snapshot, or None when no record exists.
        """
        # 1. One point read mapped to a detached snapshot.
        async with self._postgres.session() as session:
            row = await IdempotencyApi.get(
                session,
                actor_scope=actor_scope,
                method=method,
                path=path,
                idempotency_key=idempotency_key,
            )
            return IdempotencyRecord.from_row(row) if row is not None else None

    async def prune(self, cutoff: datetime) -> int:
        """
        Delete every record whose ``expires_at`` is strictly before ``cutoff`` (the GC sweep).

        Args:
            cutoff (datetime): The GC "now" — rows expiring before this are removed.

        Returns:
            int: The number of rows deleted.
        """
        # 1. Age-based bulk delete inside one committed session.
        async with self._postgres.session() as session:
            deleted = await IdempotencyApi.prune(session, cutoff)
        if deleted:
            self.logger.info(
                f"Idempotency GC pruned {deleted} expired record(s) (cutoff {cutoff.isoformat()})"
            )
        return deleted


__all__ = ["IdempotencyFacade"]
