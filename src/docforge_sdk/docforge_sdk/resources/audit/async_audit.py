# ====== Code Summary ======
# The asynchronous root-only audit-trail reads resource: the awaiting shell over the shared
# ``_AuditSpecs`` builders.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Local Project Imports ======
from ...models.audit import AuditPage
from .._base import AsyncResource
from .specs import _AuditSpecs


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
