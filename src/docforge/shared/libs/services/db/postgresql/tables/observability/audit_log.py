# ====== Code Summary ======
# The `audit_log` table — an append-only trail of every mutating /api/v1 action: who did it, when,
# to what, and the outcome. A request-scoped middleware INSERTs exactly one row per successful or
# failed mutation; a root-only endpoint reads it back paginated and filtered. The row is a permanent
# HISTORICAL FACT, so it deliberately holds no hard foreign keys — the actor ids are stored raw and
# must outlive deletion of the user/key they reference (deleting an actor must never be blocked by,
# nor erase, its audit history).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import BigInteger, Identity, Index, SmallInteger, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin


class AuditLog(Base, CreatedAtMixin):
    """One immutable audit-trail row per mutating API action (actor, target, outcome)."""

    __tablename__ = "audit_log"
    # Read-path indexes for the root-only audit endpoint's filters + the retention prune. All are plain
    # btree indexes leading with (or ending on) ``created_at DESC`` because the endpoint always orders
    # newest-first and range-filters by event time, and the age-based retention sweep prunes by
    # ``created_at``. The DESC composites are declared here with ``text("created_at DESC")`` — the same
    # form already proven to reconcile cleanly under ``--autogenerate`` on ``job`` / ``document`` — so
    # Alembic does not try to drop them.
    __table_args__ = (
        # Global newest-first listing + created_at range filter + retention prune by age.
        Index("ix_audit_log_created_at", text("created_at DESC")),
        # "What did this API key do", newest-first.
        Index("ix_audit_log_actor_key_created", "actor_key_id", text("created_at DESC")),
        # "What did this user do", newest-first.
        Index("ix_audit_log_actor_user_created", "actor_user_id", text("created_at DESC")),
        # "Full history of this resource", newest-first.
        Index(
            "ix_audit_log_target_created",
            "target_type",
            "target_id",
            text("created_at DESC"),
        ),
        # Trace every audit row emitted for one request id (0.9.8 correlation id).
        Index("ix_audit_log_correlation_id", "correlation_id"),
    )

    # BIGINT IDENTITY rather than the schema's usual app-generated UUID v4: this table is append-heavy
    # and never referenced by a foreign key, so a monotonic server-generated key gives sequential btree
    # insert locality (no random-UUID page-split churn on the hot INSERT path) and a natural, stable
    # tiebreaker for keyset pagination when many rows share the same ``created_at`` under a burst
    # (ORDER BY created_at DESC, id DESC). The middleware need not generate an id at all.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)

    # Actor identity — stored RAW with NO foreign key. The audit row must survive (and must never
    # block) deletion of the user/key it names, and it keeps the original id for forensics even after
    # that actor is gone; ``actor_label`` is the human-readable fallback so the log reads without joins.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # The action: HTTP method + the low-cardinality ROUTE TEMPLATE (e.g.
    # "/api/v1/collections/{id}/reingest"), never the raw path with concrete ids.
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)

    # The primary resource acted on, parsed from the path by the middleware (e.g. "collection" + uuid).
    # ``target_id`` is text because a target may be keyed by uuid, slug, or composite string.
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Outcome. SMALLINT comfortably holds any HTTP status code (well under 32767).
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Ties every audit row of one request together (the correlation id shipped in 0.9.8).
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # XFF-aware client ip; String(45) fits a full IPv6 textual address.
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)


__all__ = ["AuditLog"]
