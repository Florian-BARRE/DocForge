# ====== Code Summary ======
# AuditApi — the data-access API for the append-only `audit_log` table: INSERT one row (the write the
# app's audit middleware performs after every mutating request), read it back as a keyset-paginated
# page under a set of optional filters (the root-only audit endpoint), and age-prune it (the worker
# retention cron). Postgres-only, session-driven — the AuditFacade composes it. The read always orders
# newest-first by (created_at DESC, id DESC), the exact composite the table's indexes lead with, and
# keyset-pages with a strict row-value comparison so a burst sharing one created_at never skips or
# duplicates a row across pages.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import AuditLog


class AuditApi:
    """Static data-access API for the append-only audit-log table."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuditApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        method: str,
        path: str,
        status_code: int,
        actor_user_id: uuid.UUID | None = None,
        actor_key_id: uuid.UUID | None = None,
        actor_label: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        client_ip: str | None = None,
    ) -> AuditLog:
        """
        Insert one audit-trail row and return it (flushed, so its server id/created_at are populated).

        Args:
            session (AsyncSession): The active session.
            method (str): The request's HTTP method.
            path (str): The matched route TEMPLATE (never the raw concrete path).
            status_code (int): The response status code.
            actor_user_id (uuid.UUID | None): The acting user's id, when known.
            actor_key_id (uuid.UUID | None): The acting API key's id, when known.
            actor_label (str | None): Human-readable actor label (key name / username / "root").
            target_type (str | None): The primary resource type acted on (e.g. "collection").
            target_id (str | None): The primary resource id, parsed from the concrete path.
            correlation_id (str | None): The request's correlation id.
            client_ip (str | None): The XFF-aware client ip.

        Returns:
            AuditLog: The persisted row.
        """
        # 1. Build the row — id (BIGINT IDENTITY) and created_at (server default) are DB-generated.
        row = AuditLog(
            method=method,
            path=path,
            status_code=status_code,
            actor_user_id=actor_user_id,
            actor_key_id=actor_key_id,
            actor_label=actor_label,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id,
            client_ip=client_ip,
        )
        # 2. Add + flush so the server-generated id/created_at are available on return.
        session.add(row)
        await session.flush()
        return row

    @staticmethod
    async def list_page(
        session: AsyncSession,
        *,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: int | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_key_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[AuditLog]:
        """
        Return one newest-first page of audit rows matching the given filters (keyset-paginated).

        Args:
            session (AsyncSession): The active session.
            limit (int): Maximum rows to return (the caller has already clamped it).
            cursor_created_at (datetime | None): The last row's created_at from the previous page.
            cursor_id (int | None): The last row's id from the previous page (the DESC tiebreaker).
            actor_user_id (uuid.UUID | None): Filter to one acting user.
            actor_key_id (uuid.UUID | None): Filter to one acting API key.
            target_type (str | None): Filter to one target type (requires nothing else).
            target_id (str | None): Filter to one target id (paired with ``target_type``).
            correlation_id (str | None): Filter to one request's correlation id.
            created_from (datetime | None): Lower bound (inclusive) on created_at.
            created_to (datetime | None): Upper bound (exclusive) on created_at.

        Returns:
            list[AuditLog]: The page, ordered created_at DESC, id DESC.
        """
        # 1. Base query — always newest-first with the id tiebreaker (matches the leading index).
        query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

        # 2. Equality filters — each narrows to a single actor / target / correlation.
        if actor_user_id is not None:
            query = query.where(AuditLog.actor_user_id == actor_user_id)
        if actor_key_id is not None:
            query = query.where(AuditLog.actor_key_id == actor_key_id)
        if target_type is not None:
            query = query.where(AuditLog.target_type == target_type)
        if target_id is not None:
            query = query.where(AuditLog.target_id == target_id)
        if correlation_id is not None:
            query = query.where(AuditLog.correlation_id == correlation_id)

        # 3. Event-time range window (from inclusive, to exclusive).
        if created_from is not None:
            query = query.where(AuditLog.created_at >= created_from)
        if created_to is not None:
            query = query.where(AuditLog.created_at < created_to)

        # 4. Keyset predicate — strictly "older than" the cursor row under the DESC ordering. A
        #    row-value comparison keeps the (created_at, id) tiebreak exact under a same-instant burst.
        if cursor_created_at is not None and cursor_id is not None:
            query = query.where(
                tuple_(AuditLog.created_at, AuditLog.id) < tuple_(cursor_created_at, cursor_id)
            )

        # 5. One bounded page.
        result = await session.execute(query.limit(limit))
        return list(result.scalars().all())

    @staticmethod
    async def prune(session: AsyncSession, cutoff: datetime) -> int:
        """
        Delete every audit row older than ``cutoff`` and return how many were removed.

        Args:
            session (AsyncSession): The active session.
            cutoff (datetime): Rows with ``created_at`` strictly before this are deleted.

        Returns:
            int: The number of rows deleted.
        """
        # 1. Age-based bulk delete — the leading created_at index bounds the scan.
        result = await session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
        return result.rowcount or 0


__all__ = ["AuditApi"]
