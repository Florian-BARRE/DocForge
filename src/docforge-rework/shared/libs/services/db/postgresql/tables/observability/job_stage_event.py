# ====== Code Summary ======
# The `job_stage_event` table — the per-stage timeline of a job (one row per stage transition), so
# the UI can show a live, staged progress view (parse done, enrich running, chunk pending) rather
# than a single percentage.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["JobStageEvent"]
