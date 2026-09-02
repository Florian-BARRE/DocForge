# ====== Code Summary ======
# The audit resource — the root-only read over the append-only audit trail. All URL/param logic lives
# once in the pure _AuditSpecs mixin so AsyncAudit and SyncAudit differ ONLY by ``await``. Every
# filter (actor, target, correlation id, event-time window) and the keyset cursor are query
# parameters, threaded through the spec's params (omitted when None so the server applies its default).

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.audit import AuditPage
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _AuditSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the audit endpoint — the single source of URL/param logic."""

    _AUDIT_PATH = "/audit"

    def _list_spec(
        self,
        limit: int | None = None,
        cursor: str | None = None,
        actor_user_id: str | None = None,
        actor_key_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> RequestSpec:
        """
        Build the spec for one keyset-paginated, filtered page of the audit trail.

        Args:
            limit (int | None): Page size; the server clamps it to its ceiling. Omitted → default.
            cursor (str | None): Opaque cursor from a previous page's ``next_cursor``.
            actor_user_id (str | None): Filter to one acting user.
            actor_key_id (str | None): Filter to one acting API key.
            target_type (str | None): Filter to one target type (e.g. "collection").
            target_id (str | None): Filter to one target id (pair with ``target_type``).
            correlation_id (str | None): Filter to one request's correlation id.
            created_from (datetime | None): Lower bound (inclusive) on created_at.
            created_to (datetime | None): Upper bound (exclusive) on created_at.

        Returns:
            RequestSpec: A GET on ``/audit`` carrying the supplied filters + paging as query params.
        """
        # 1. Only the supplied filters ride the wire (None → omitted so the server default applies).
        params: dict[str, object] = {}
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        if actor_user_id is not None:
            params["actor_user_id"] = actor_user_id
        if actor_key_id is not None:
            params["actor_key_id"] = actor_key_id
        if target_type is not None:
            params["target_type"] = target_type
        if target_id is not None:
            params["target_id"] = target_id
        if correlation_id is not None:
            params["correlation_id"] = correlation_id
        if created_from is not None:
            params["created_from"] = created_from.isoformat()
        if created_to is not None:
            params["created_to"] = created_to.isoformat()
        return RequestSpec("GET", self._AUDIT_PATH, params=params)


class AsyncAudit(AsyncResource, _AuditSpecs):
    """Asynchronous root-only audit-trail reads."""

    async def list(
        self,
        limit: int | None = None,
        cursor: str | None = None,
        actor_user_id: str | None = None,
        actor_key_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AuditPage:
        """
        List one keyset-paginated page of the audit trail, newest first (ROOT/full-access only).

        Args:
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            cursor (str | None): Opaque cursor from a previous page's ``next_cursor``.
            actor_user_id (str | None): Filter to one acting user.
            actor_key_id (str | None): Filter to one acting API key.
            target_type (str | None): Filter to one target type (e.g. "collection").
            target_id (str | None): Filter to one target id (pair with ``target_type``).
            correlation_id (str | None): Filter to one request's correlation id.
            created_from (datetime | None): Lower bound (inclusive) on created_at.
            created_to (datetime | None): Upper bound (exclusive) on created_at.

        Returns:
            AuditPage: The page (``.entries``) plus ``limit`` and the ``next_cursor`` for paging.
        """
        return await self._transport.request(
            self._list_spec(
                limit,
                cursor,
                actor_user_id,
                actor_key_id,
                target_type,
                target_id,
                correlation_id,
                created_from,
                created_to,
            ),
            AuditPage,
        )


class SyncAudit(SyncResource, _AuditSpecs):
    """Synchronous root-only audit-trail reads."""

    def list(
        self,
        limit: int | None = None,
        cursor: str | None = None,
        actor_user_id: str | None = None,
        actor_key_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AuditPage:
        """
        List one keyset-paginated page of the audit trail, newest first (ROOT/full-access only).

        Args:
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            cursor (str | None): Opaque cursor from a previous page's ``next_cursor``.
            actor_user_id (str | None): Filter to one acting user.
            actor_key_id (str | None): Filter to one acting API key.
            target_type (str | None): Filter to one target type (e.g. "collection").
            target_id (str | None): Filter to one target id (pair with ``target_type``).
            correlation_id (str | None): Filter to one request's correlation id.
            created_from (datetime | None): Lower bound (inclusive) on created_at.
            created_to (datetime | None): Upper bound (exclusive) on created_at.

        Returns:
            AuditPage: The page (``.entries``) plus ``limit`` and the ``next_cursor`` for paging.
        """
        return self._transport.request(
            self._list_spec(
                limit,
                cursor,
                actor_user_id,
                actor_key_id,
                target_type,
                target_id,
                correlation_id,
                created_from,
                created_to,
            ),
            AuditPage,
        )


__all__ = ["AsyncAudit", "SyncAudit"]
