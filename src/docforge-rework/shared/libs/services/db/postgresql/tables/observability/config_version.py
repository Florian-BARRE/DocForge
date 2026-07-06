# ====== Code Summary ======
# The `config_version` table — an append-only history of a collection's configuration. A new row is
# written on every config change, so the config can be listed, audited and rolled back.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, UUIDPrimaryKey


class ConfigVersion(Base, UUIDPrimaryKey, CreatedAtMixin):
    """An immutable snapshot of a collection's config."""

    __tablename__ = "config_version"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


__all__ = ["ConfigVersion"]
