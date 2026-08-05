# ====== Code Summary ======
# The `job_stage_event` table — the per-stage timeline of a job (one row per stage transition), so
# the UI can show a live, staged progress view (parse done, enrich running, chunk pending) rather
# than a single percentage.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
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


__all__ = ["JobStageEvent"]
