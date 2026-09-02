# ====== Code Summary ======
# AuditFacade — the data-layer gateway for the append-only audit trail. The app's audit middleware
# calls `record(...)` once per mutating request (fail-safe: the caller swallows any error so the
# user's request is never affected); the root-only audit endpoint calls `list(...)` for a
# keyset-paginated, filtered page; and the worker retention cron calls `prune(cutoff)` to age out old
# rows. Postgres-only — it composes AuditApi inside one transactional session per call.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import AuditApi
from shared_libs.services.db.postgresql.tables import AuditLog


class AuditFacade(LoggerClass):
    """Record, read, and age-prune the append-only audit trail."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth store.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def record(
        self,
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
    ) -> None:
        """
        Insert one audit-trail row for a mutating API action.

        The caller (the audit middleware) treats this as best-effort — it catches and swallows any
        error so audit availability never affects the user's request outcome.

        Args:
            method (str): The request's HTTP method.
            path (str): The matched route TEMPLATE.
            status_code (int): The response status code.
            actor_user_id (uuid.UUID | None): The acting user's id, when known.
            actor_key_id (uuid.UUID | None): The acting API key's id, when known.
            actor_label (str | None): Human-readable actor label.
            target_type (str | None): The primary resource type acted on.
            target_id (str | None): The primary resource id.
            correlation_id (str | None): The request's correlation id.
            client_ip (str | None): The XFF-aware client ip.
        """
        # 1. One INSERT inside a committed session (id + created_at are server-generated).
        async with self._postgres.session() as session:
            await AuditApi.create(
                session,
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

    async def list(
        self,
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
        Return one newest-first, keyset-paginated page of audit rows under the given filters.

        Args:
            limit (int): Maximum rows to return (already clamped by the caller).
            cursor_created_at (datetime | None): The previous page's last created_at.
            cursor_id (int | None): The previous page's last id (the DESC tiebreaker).
            actor_user_id (uuid.UUID | None): Filter to one acting user.
            actor_key_id (uuid.UUID | None): Filter to one acting API key.
            target_type (str | None): Filter to one target type.
            target_id (str | None): Filter to one target id.
            correlation_id (str | None): Filter to one request's correlation id.
            created_from (datetime | None): Lower bound (inclusive) on created_at.
            created_to (datetime | None): Upper bound (exclusive) on created_at.

        Returns:
            list[AuditLog]: The page, ordered created_at DESC, id DESC.
        """
        # 1. One bounded, filtered, keyset read.
        async with self._postgres.session() as session:
            return await AuditApi.list_page(
                session,
                limit=limit,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
                actor_user_id=actor_user_id,
                actor_key_id=actor_key_id,
                target_type=target_type,
                target_id=target_id,
                correlation_id=correlation_id,
                created_from=created_from,
                created_to=created_to,
            )

    async def prune(self, cutoff: datetime) -> int:
        """
        Delete every audit row older than ``cutoff`` (the retention sweep) and log the count.

        Args:
            cutoff (datetime): Rows with ``created_at`` strictly before this are removed.

        Returns:
            int: The number of rows deleted.
        """
        # 1. Age-based bulk delete inside one committed session.
        async with self._postgres.session() as session:
            deleted = await AuditApi.prune(session, cutoff)
        if deleted:
            self.logger.info(
                f"Audit retention pruned {deleted} row(s) older than {cutoff.isoformat()}"
            )
        return deleted


__all__ = ["AuditFacade"]
