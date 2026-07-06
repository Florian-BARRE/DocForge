# ====== Code Summary ======
# The `enrichment_attempt` table — the TRACE of an enrichment: one row per model tried, in order,
# including the ones that FAILED before a later model succeeded. This is the persisted view of the
# engine's escalation chain (its NodeExecutionRecord): "olmOCR failed → Mistral OCR succeeded". It
# answers, for any OCR/VLM/… result, exactly which chain of models produced it.

# ====== Standard Library Imports ======
import uuid
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, UUIDPrimaryKey, value_enum


class AttemptStatus(StrEnum):
    """Outcome of a single model attempt in the chain."""

    OK = "ok"
    FAILED = "failed"


class EnrichmentAttempt(Base, UUIDPrimaryKey, CreatedAtMixin):
    """One model attempt within an enrichment's escalation chain."""

    __tablename__ = "enrichment_attempt"

    block_enrichment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("block_enrichment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # order in the chain (0-based)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AttemptStatus] = mapped_column(value_enum(AttemptStatus), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


__all__ = ["EnrichmentAttempt", "AttemptStatus"]
