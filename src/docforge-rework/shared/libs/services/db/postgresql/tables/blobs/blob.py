# ====== Code Summary ======
# The `blob` table — the Postgres index of the S3 object store. Content-addressed: the blob's
# content hash is its primary key, so an identical byte-stream (a repeated logo, the same file
# re-uploaded) is stored once. Documents, pages and figures reference their bytes by this hash — it
# is the lineage seam between the tabular truth (Postgres) and the blobs (S3).

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, value_enum


class BlobKind(StrEnum):
    """What a stored blob is."""

    ORIGINAL = "original"            # the uploaded source file
    CANONICAL_PDF = "canonical_pdf"  # the PDF view after conversion
    PAGE_RENDER = "page_render"      # a rasterized page image
    FIGURE_CROP = "figure_crop"      # a cropped figure image


class Blob(Base, CreatedAtMixin):
    """A content-addressed object in S3, indexed in Postgres."""

    __tablename__ = "blob"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[BlobKind] = mapped_column(value_enum(BlobKind), nullable=False)


__all__ = ["Blob", "BlobKind"]
