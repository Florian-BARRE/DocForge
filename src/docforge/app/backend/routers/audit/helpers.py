# ====== Code Summary ======
# AuditReadHelpers — the pure encode/decode + mapping helpers the root-only audit endpoint leans on:
# an opaque keyset cursor (base64 of the last row's created_at + id) that the client passes back
# verbatim, and the AuditLog row → AuditEntry response mapper. Kept out of the router so the route
# body stays a thin gate + delegation.

# ====== Standard Library Imports ======
from __future__ import annotations

import base64
import binascii
from datetime import datetime

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import AuditLog

# ====== Local Project Imports ======
from .models import AuditEntry

# Separates the two cursor components inside the pre-base64 payload; not valid in an ISO timestamp.
_CURSOR_SEP = "|"


class AuditReadHelpers:
    """Static helpers for the audit read endpoint (cursor codec + row mapping)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuditReadHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def encode_cursor(created_at: datetime, row_id: int) -> str:
        """
        Encode a keyset cursor from a row's ``(created_at, id)`` into an opaque token.

        Args:
            created_at (datetime): The row's created_at.
            row_id (int): The row's id (the DESC tiebreaker).

        Returns:
            str: A url-safe base64 token the client passes back as ``cursor``.
        """
        # 1. Pack the two ordering components, then base64 them so the client treats it as opaque.
        raw = f"{created_at.isoformat()}{_CURSOR_SEP}{row_id}".encode()
        return base64.urlsafe_b64encode(raw).decode()

    @staticmethod
    def decode_cursor(cursor: str) -> tuple[datetime, int]:
        """
        Decode an opaque keyset cursor back into its ``(created_at, id)`` components.

        Args:
            cursor (str): The token a previous page returned as ``next_cursor``.

        Returns:
            tuple[datetime, int]: The created_at + id to page strictly older than.

        Raises:
            HTTPException: 400 when the token is malformed (never a 500).
        """
        # 1. Reverse the base64 + split; any malformed token is a client error (400), not a crash.
        try:
            raw = base64.urlsafe_b64decode(cursor.encode()).decode()
            timestamp, _, row_id = raw.rpartition(_CURSOR_SEP)
            return datetime.fromisoformat(timestamp), int(row_id)
        except (ValueError, binascii.Error):
            raise HTTPException(status_code=400, detail="Malformed audit cursor.")

    @staticmethod
    def to_entry(row: AuditLog) -> AuditEntry:
        """
        Map one AuditLog table row to its AuditEntry response model.

        Args:
            row (AuditLog): The persisted audit row.

        Returns:
            AuditEntry: The API representation (uuids stringified).
        """
        # 1. Stringify the uuid columns; everything else maps straight across.
        return AuditEntry(
            id=row.id,
            created_at=row.created_at,
            method=row.method,
            path=row.path,
            status_code=row.status_code,
            actor_user_id=str(row.actor_user_id) if row.actor_user_id is not None else None,
            actor_key_id=str(row.actor_key_id) if row.actor_key_id is not None else None,
            actor_label=row.actor_label,
            target_type=row.target_type,
            target_id=row.target_id,
            correlation_id=row.correlation_id,
            client_ip=row.client_ip,
        )


__all__ = ["AuditReadHelpers"]
