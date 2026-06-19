# ====== Code Summary ======
# SQLAlchemy ORM model for the provider-call cache (P2 stage engine).
# Deduplicates expensive OCR/VLM/embed calls across documents using a content
# fingerprint as the primary key.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from .base import Base


class ProviderCallModel(Base):
    """
    Provider-call cache (P2 stage engine).

    Deduplicates expensive OCR/VLM/embed calls across documents.
    Key: blake3(capability, provider_id, provider_version, params, content_hash).
    """

    __tablename__ = "provider_call"

    call_fp: Mapped[str] = mapped_column(String(128), primary_key=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
