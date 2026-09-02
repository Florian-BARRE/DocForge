# ====== Code Summary ======
# The audit router — a single ROOT/full-access-only read over the append-only audit trail. The
# middleware writes the rows; this endpoint serves them back newest-first, keyset-paginated and
# filterable (by actor, target, correlation id, and an event-time window). Business logic (cursor
# codec + row mapping) lives in helpers; the route body is a thin authz gate + delegation to the
# audit façade on CONTEXT.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Query

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, Capability, require
from ...utils.error_handling import auto_handle_errors
from .helpers import AuditReadHelpers
from .models import AuditPage

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
@auto_handle_errors
async def list_audit(
    limit: int = Query(
        default=RUNTIME_CONFIG.AUDIT_MAX_PAGE_SIZE,
        ge=1,
        description="Page size, clamped down to AUDIT_MAX_PAGE_SIZE. Defaults to that ceiling.",
    ),
    cursor: str | None = Query(
        default=None, description="Opaque keyset cursor from a previous page's next_cursor."
    ),
    actor_user_id: uuid.UUID | None = Query(default=None, description="Filter to one acting user."),
    actor_key_id: uuid.UUID | None = Query(
        default=None, description="Filter to one acting API key."
    ),
    target_type: str | None = Query(
        default=None, description="Filter to one target type (e.g. 'collection')."
    ),
    target_id: str | None = Query(
        default=None, description="Filter to one target id (pair with target_type)."
    ),
    correlation_id: str | None = Query(
        default=None, description="Filter to one request's correlation id."
    ),
    created_from: datetime | None = Query(
        default=None, description="Lower bound (inclusive) on created_at."
    ),
    created_to: datetime | None = Query(
        default=None, description="Upper bound (exclusive) on created_at."
    ),
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> AuditPage:
    """
    Return one newest-first, keyset-paginated page of the audit trail (ROOT/full-access only).

    The trail spans every tenant, so it is restricted to a full-access (root / unscoped) key — a
    collection-scoped key is rejected with 403, mirroring how fleet-wide job counts are gated. Filter
    by actor, target, correlation id, and an event-time window; page with the opaque ``next_cursor``.

    Returns:
        AuditPage: The page of rows + the applied limit + the next-page cursor (null when exhausted).
    """
    # 1. Fleet-wide surface → full-access only (a scoped key can never read the cross-tenant trail).
    if not principal.is_full_access:
        raise HTTPException(
            status_code=403, detail="The audit trail is restricted to full-access keys."
        )

    # 2. Clamp the page size so a client can never demand an unbounded scan of the append-only table.
    page_size = min(limit, RUNTIME_CONFIG.AUDIT_MAX_PAGE_SIZE)

    # 3. Decode the keyset cursor (a malformed token is a 400, not a crash).
    cursor_created_at, cursor_id = (None, None)
    if cursor is not None:
        cursor_created_at, cursor_id = AuditReadHelpers.decode_cursor(cursor)

    # 4. Over-fetch one row to detect whether a further page exists without a second count query.
    rows = await CONTEXT.database.audit.list(
        limit=page_size + 1,
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

    # 5. Trim the sentinel row; when it was present, the last kept row seeds the next-page cursor.
    has_more = len(rows) > page_size
    page = rows[:page_size]
    next_cursor = (
        AuditReadHelpers.encode_cursor(page[-1].created_at, page[-1].id)
        if has_more and page
        else None
    )
    return AuditPage(
        entries=[AuditReadHelpers.to_entry(row) for row in page],
        limit=page_size,
        next_cursor=next_cursor,
    )


__all__ = ["router"]
