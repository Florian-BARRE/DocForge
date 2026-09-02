# ====== Code Summary ======
# Response models for the root-only audit endpoint, mirrored field-for-field from the DocForge
# backend router models (audit/models.py): one immutable audit row (AuditEntry) and the
# keyset-paginated page envelope (AuditPage) carrying a page of rows plus the opaque next cursor.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """
    One immutable audit-trail row — who did what mutating action, to what, and the outcome.

    Attributes:
        id (int): The row's monotonic server-generated id (also the keyset tiebreaker).
        created_at (datetime): When the action was recorded (server clock).
        method (str): The request's HTTP method.
        path (str): The matched route template (never the raw concrete path with ids).
        status_code (int): The response status code.
        actor_user_id (str | None): The acting user's id, when known.
        actor_key_id (str | None): The acting API key's id, when known.
        actor_label (str | None): Human-readable actor label (key name / username / "root").
        target_type (str | None): The primary resource type acted on (e.g. "collection").
        target_id (str | None): The primary resource id, parsed from the concrete path.
        correlation_id (str | None): The request's correlation id (ties app + worker log lines).
        client_ip (str | None): The XFF-aware client ip.
    """

    id: int = Field(description="The row's monotonic server id (also the keyset tiebreaker).")
    created_at: datetime = Field(description="When the action was recorded (server clock).")
    method: str = Field(description="The request's HTTP method.")
    path: str = Field(description="The matched route template (never the raw concrete path).")
    status_code: int = Field(description="The response status code.")
    actor_user_id: str | None = Field(default=None, description="The acting user's id, when known.")
    actor_key_id: str | None = Field(
        default=None, description="The acting API key's id, when known."
    )
    actor_label: str | None = Field(
        default=None, description="Human-readable actor label (key name / username / 'root')."
    )
    target_type: str | None = Field(
        default=None, description="The primary resource type acted on (e.g. 'collection')."
    )
    target_id: str | None = Field(
        default=None, description="The primary resource id, parsed from the concrete path."
    )
    correlation_id: str | None = Field(
        default=None, description="The request's correlation id (ties app + worker log lines)."
    )
    client_ip: str | None = Field(default=None, description="The XFF-aware client ip.")


class AuditPage(BaseModel):
    """
    One newest-first, keyset-paginated page of the audit trail.

    Pass ``next_cursor`` back as ``cursor`` to fetch the next page; a null ``next_cursor`` means the
    trail is exhausted.

    Attributes:
        entries (list[AuditEntry]): The page of rows, newest first.
        limit (int): The applied page size (after the server ceiling clamp).
        next_cursor (str | None): Opaque cursor for the next page, or null when exhausted.
    """

    entries: list[AuditEntry] = Field(description="The page of audit rows, newest first.")
    limit: int = Field(description="The applied page size (after the server ceiling clamp).")
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page (null when exhausted)."
    )


__all__ = ["AuditEntry", "AuditPage"]
