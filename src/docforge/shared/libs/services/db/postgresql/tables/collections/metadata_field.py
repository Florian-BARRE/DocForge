# ====== Code Summary ======
# The `metadata_field` table — one row per field of a collection's metadata SCHEMA. Each row fixes a
# field's type, whether it is required at upload, its three orthogonal searchability flags
# (filterable → Qdrant payload filter, lexical → sparse BM25 vector, semantic → dense vector), its
# origin (who fills it: user / system / generated) and its SCOPE (where the value lives: one per
# document, or one per CHUNK — the post-chunk LLM generation). Declaring every field — including the
# chunk-generated ones — at collection creation is what lets the Qdrant vector space be complete
# from day one (named vectors cannot be added later without a reindex). Two DB-level integrity
# rules: `required` only makes sense for user-supplied fields, and chunk scope only for generated.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType

# ====== Local Project Imports ======
from ..base import Base, value_enum


class MetadataField(Base):
    """One field of a collection's metadata schema."""

    __tablename__ = "metadata_field"
    __table_args__ = (
        UniqueConstraint("collection_id", "field_name"),
        # A field can only be required from the caller — system/generated fields are filled later.
        CheckConstraint("NOT required OR origin = 'user'", name="required_user_only"),
        # A per-chunk value can only come from post-chunk generation.
        CheckConstraint(
            "scope != 'chunk' OR origin = 'generated'", name="chunk_scope_generated_only"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[FieldType] = mapped_column(value_enum(FieldType), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lexical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    semantic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enum_values: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    origin: Mapped[FieldOrigin] = mapped_column(
        value_enum(FieldOrigin), nullable=False, default=FieldOrigin.USER
    )
    scope: Mapped[FieldScope] = mapped_column(
        value_enum(FieldScope), nullable=False, default=FieldScope.DOCUMENT
    )


__all__ = ["MetadataField"]
