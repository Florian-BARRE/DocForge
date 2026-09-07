# ====== Code Summary ======
# The `job_stage_event` table — the per-stage timeline of a job (one row per stage transition), so
# the UI can show a live, staged progress view (parse done, enrich running, chunk pending) rather
# than a single percentage.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from decimal import Decimal

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, UUIDPrimaryKey


class JobStageEvent(Base, UUIDPrimaryKey, CreatedAtMixin):
    """One stage transition within a job's timeline."""

    __tablename__ = "job_stage_event"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Type label for this stage's root node — the structural kind (action/group/foreach) or the
    # node's concrete kind — so the UI can render what each stage actually is. NULL for pre-existing
    # rows written before this column landed.
    node_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Paid text-gen token/cost meter for this stage (NULL when the stage made no paid call, or the
    # cost when its model is unknown to the pricing table — tokens still recorded).
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # ── Execution-tree columns (materialized-path model, no self-FK) ──────────────────────────────
    # These let a single job_stage_event row locate itself in the FULL per-node execution tree — every
    # node, including nested group children and per-item ForEach body instances — not just the flat
    # per-root-stage timeline. Root rows are the existing live rows; nested rows are inserted post-run.
    # The UI reconstructs the tree from ``node_path`` + ``depth``. All are nullable with NO
    # server_default: legacy rows written before this landed read NULL and fall back to the flat model.
    node_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Materialized path of this node in the execution tree.

    Root nodes use their bare node id (e.g. ``parse``); nested nodes use a dotted/bracketed path down
    from the root (e.g. ``enrich.figures[3].vlm``). NULL marks a legacy row written before this column
    existed — the API then falls back to ``stage`` for identity.
    """

    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Depth of this node in the execution tree.

    ``0`` is a root stage; larger values are progressively more nested (group children, ForEach body
    instances). NULL marks a legacy row and is treated as ``0`` by the read side.
    """

    parent_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    """``node_path`` of this node's parent in the execution tree.

    NULL for root nodes (which have no parent) and for legacy rows written before this column existed.
    """

    item_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Zero-based ForEach item index when this row is a per-item body instance.

    Set only for nodes running inside a ForEach fan-out, to distinguish the per-item copies of the same
    body node; NULL for any node that is not a ForEach body instance (and for legacy rows).
    """

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Quality score of a ``scored``-family node, in ``[0, 1]``.

    Populated for nodes whose family is scored (parser ``docling``/``granite_docling``/``pp_structure``,
    ``ocr``, …), where it drives ``ScoreBelow`` escalation. NULL for non-scored nodes and legacy rows.
    Stored as double precision (SQLAlchemy ``Float``): a ``[0, 1]`` quality score needs no exact-decimal
    representation, unlike the monetary ``cost_usd`` (``Numeric``); this matches the FLOAT resource
    samples elsewhere in the observability domain.
    """


__all__ = ["JobStageEvent"]
