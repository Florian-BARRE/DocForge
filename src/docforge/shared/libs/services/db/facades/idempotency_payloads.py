# ====== Code Summary ======
# Detached, session-independent snapshots the IdempotencyFacade hands back to the app's middleware.
# The ORM row lives only inside the façade's session; the middleware needs a plain immutable value it
# can read after that session has closed (state + fingerprint for the decision, the cached response
# for replay). `IdempotencyRecord` is that snapshot; `IdempotencyBegin` wraps the outcome of the
# guard INSERT — whether THIS request won the race (created) and the current record either way.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import IdempotencyKey, IdempotencyState


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """
    A detached snapshot of one idempotency row — everything the middleware's decision needs.

    Attributes:
        state (IdempotencyState): ``in_progress`` (a request is still running) or ``completed``.
        request_fingerprint (str): sha256 hex of the original request body (mismatch → 422).
        response_status (int | None): The cached response status (set once completed).
        response_body (bytes | None): The cached response body bytes (set once completed).
        response_media_type (str | None): The cached response content-type (set once completed).
    """

    state: IdempotencyState
    request_fingerprint: str
    response_status: int | None
    response_body: bytes | None
    response_media_type: str | None

    @classmethod
    def from_row(cls, row: IdempotencyKey) -> IdempotencyRecord:
        """
        Build an immutable snapshot from a live ORM row (read while the session is still open).

        Args:
            row (IdempotencyKey): The persisted idempotency row.

        Returns:
            IdempotencyRecord: The detached snapshot safe to read after the session closes.
        """
        # 1. Copy exactly the fields the replay/reuse decision reads — nothing session-bound.
        return cls(
            state=row.state,
            request_fingerprint=row.request_fingerprint,
            response_status=row.response_status,
            response_body=row.response_body,
            response_media_type=row.response_media_type,
        )


@dataclass(frozen=True, slots=True)
class IdempotencyBegin:
    """
    The outcome of the guard INSERT: did THIS request win the race, and the current record.

    Attributes:
        created (bool): True when this request won the INSERT (it must now run the handler); False
            when the row already existed (replay / conflict / in-progress — never run the handler).
        record (IdempotencyRecord | None): The current record. On ``created`` it is the fresh
            in-progress snapshot; on conflict it is the existing row (None only if it vanished between
            the failed INSERT and the follow-up read — treated as in-progress by the caller).
    """

    created: bool
    record: IdempotencyRecord | None


__all__ = ["IdempotencyRecord", "IdempotencyBegin"]
