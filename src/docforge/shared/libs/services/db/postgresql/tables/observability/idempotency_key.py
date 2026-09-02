# ====== Code Summary ======
# The `idempotency_key` table — a Stripe-style Idempotency-Key store. On a mutating POST that carries
# an ``Idempotency-Key`` header, a request-scoped middleware looks up (or INSERTs) exactly one row per
# (actor, endpoint, key), runs the handler at most once, and caches the response so retries replay the
# cached outcome instead of re-executing. The UNIQUE key doubles as the concurrency guard: two
# simultaneous first-requests race to INSERT and the loser catches the unique violation (treated as
# "already in progress").

# ====== Standard Library Imports ======
from datetime import datetime
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, value_enum


class IdempotencyState(StrEnum):
    """Lifecycle of a single idempotency record."""

    # The first request won the INSERT and is running its handler; response is not cached yet.
    in_progress = "in_progress"
    # The handler finished; ``response_status`` / ``response_body`` / ``response_media_type`` are set
    # and any retry carrying the same key replays them verbatim.
    completed = "completed"


class IdempotencyKey(Base, CreatedAtMixin):
    """One idempotency record per (actor, method+route, client key): guard + cached response."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        # THE dedup key AND the lookup index AND the concurrency guard. Scoped by ``actor_scope`` so
        # one tenant's key never dedups against another's; by ``method`` + ``path`` (the ROUTE
        # TEMPLATE) so the same client key on two different endpoints does not collide. Because it is a
        # real UNIQUE constraint, two concurrent first-requests race to INSERT and the loser gets an
        # IntegrityError the middleware catches (→ "in progress", 409). Named explicitly and stably so
        # the backend can match the violation by constraint name.
        UniqueConstraint(
            "actor_scope",
            "method",
            "path",
            "idempotency_key",
            name="uq_idempotency_key_scope",
        ),
        # The retention prune sweeps ``WHERE expires_at < now()``; a plain btree on expires_at is
        # enough (no partial predicate — every row is eventually eligible).
        Index("ix_idempotency_key_expires_at", "expires_at"),
    )

    # BIGINT IDENTITY rather than the schema's usual app-generated UUID v4: this table is append-heavy
    # (one row per mutating request) and never the target of a foreign key, so a monotonic
    # server-generated key gives sequential btree insert locality on the hot INSERT path. The row's
    # *identity* for dedup is the UNIQUE constraint below, not this surrogate; the middleware need not
    # generate an id.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)

    # NEVER-NULL resolved actor identity string, e.g. "key:<uuid>", "user:<uuid>", or "anon" when auth
    # is off. Kept as text (not a nullable actor_key_id) on purpose: a NULL in the unique key would be
    # treated as distinct by Postgres and defeat dedup whenever auth is off. No foreign key — the row
    # must survive actor deletion, and the identity is fully captured here as text.
    actor_scope: Mapped[str] = mapped_column(String(160), nullable=False)

    # The client-supplied ``Idempotency-Key`` header value, verbatim.
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # The endpoint scope: HTTP method + the low-cardinality ROUTE TEMPLATE
    # ("/api/v1/collections/{id}/reingest"), so the same key on two endpoints stays distinct.
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)

    # sha256 hex of the request body. Lets the middleware detect key-reuse with a DIFFERENT body
    # (same key, mismatching fingerprint → 422) instead of wrongly replaying a stale response.
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    # Lifecycle. VARCHAR persisting the StrEnum VALUES (in_progress|completed). Python-side default so
    # the middleware inserts an in-progress row without spelling the state out; no server_default is
    # emitted, keeping the migration drift-free.
    state: Mapped[IdempotencyState] = mapped_column(
        value_enum(IdempotencyState), nullable=False, default=IdempotencyState.in_progress
    )

    # Cached response, all NULL while ``state == in_progress`` and filled atomically on completion.
    # ``response_body`` is BYTEA so any content-type round-trips byte-exact on replay (responses are
    # small JSON in practice, but bytea keeps the store content-type agnostic).
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    response_media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ``created_at`` comes from CreatedAtMixin (server default now). ``completed_at`` is stamped when
    # the handler finishes; ``expires_at`` is the TTL horizon the prune cron deletes past.
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["IdempotencyKey", "IdempotencyState"]
