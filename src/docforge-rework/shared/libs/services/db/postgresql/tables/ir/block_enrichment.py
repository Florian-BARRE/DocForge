# ====== Code Summary ======
# The `block_enrichment` table — a GENERIC enrichment of ANY block (not just figures). One row per
# (block, kind): a figure gets an `ocr` row AND a `vlm` row; a scanned text block gets an `ocr` row;
# a table gets a `table_summary` row. Each holds the result (text and/or structured data) plus its
# status. The model CHAIN that produced it — including the models that failed first — is recorded in
# `enrichment_attempt`, one row per attempt.

# ====== Standard Library Imports ======
from enum import StrEnum
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey, value_enum


class EnrichmentKind(StrEnum):
    """What an enrichment produces for a block."""

    CLASSIFY = "classify"            # figure kind (photo/chart/diagram/…)
    OCR = "ocr"                      # text extracted from the image
    VLM = "vlm"                      # a written description of the image
    CHART_TO_DATA = "chart_to_data"  # a chart's underlying data table
    TABLE_SUMMARY = "table_summary"  # an LLM summary of a table


class EnrichmentStatus(StrEnum):
    """Outcome of an enrichment."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class BlockEnrichment(Base, UUIDPrimaryKey, TimestampedMixin):
    """One enrichment (of one kind) applied to a block."""

    __tablename__ = "block_enrichment"
    __table_args__ = (UniqueConstraint("block_id", "kind"),)

    block_id: Mapped[str] = mapped_column(
        String(256), ForeignKey("block.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[EnrichmentKind] = mapped_column(value_enum(EnrichmentKind), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)   # OCR text / VLM description
    data: Mapped[Any | None] = mapped_column(JSONB, nullable=True)  # chart cells / classification detail
    status: Mapped[EnrichmentStatus] = mapped_column(
        value_enum(EnrichmentStatus), nullable=False, default=EnrichmentStatus.OK
    )


__all__ = ["BlockEnrichment", "EnrichmentKind", "EnrichmentStatus"]
