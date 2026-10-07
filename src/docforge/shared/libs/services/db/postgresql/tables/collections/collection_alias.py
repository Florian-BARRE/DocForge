# ====== Code Summary ======
# The `collection_alias` table — a stable, human slug ("chatmop") pointing at ONE collection. API keys
# and app configs name the alias instead of the collection UUID, so a collection can be rebuilt
# alongside ("chatmop-v2") and switched by re-pointing the alias, with no key or app edit. Distinct
# from the Qdrant-layer store aliases (`col_<hex>`) the rebuild_index job swaps — this is a
# deployment-level NAME for a collection, never a vector-store concept.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin

# The alias slug grammar, enforced at the API AND (as a backstop) by a CHECK constraint.
COLLECTION_ALIAS_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,62}$"


class CollectionAlias(Base, TimestampedMixin):
    """A named pointer to one collection (the name is the primary key, hence unique)."""

    __tablename__ = "collection_alias"
    # Naming convention renders this ``ck_collection_alias_name_slug``.
    __table_args__ = (CheckConstraint(f"name ~ '{COLLECTION_ALIAS_PATTERN}'", name="name_slug"),)

    name: Mapped[str] = mapped_column(String(63), primary_key=True)
    # RESTRICT, not CASCADE: deleting a collection an alias still targets would silently break every
    # key and app bound to the alias. The API refuses that delete with a 409 BEFORE any destructive
    # step; this FK is the backstop against a concurrent alias write slipping in.
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # created_at + updated_at come from TimestampedMixin


__all__ = ["COLLECTION_ALIAS_PATTERN", "CollectionAlias"]
