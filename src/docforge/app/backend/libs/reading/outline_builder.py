# ====== Code Summary ======
# OutlineBuilder — turns a document's heading blocks (reading order) into outline entries, each linked
# to the chunk that covers its position: the first chunk (chunk_index order) whose last block sits at or
# after the heading's reading order. Linking is STRUCTURAL, never by heading text — a repeated title
# ("Results" under two chapters) or a breadcrumb that skips a level cannot mis-link. Headings and chunks
# are both monotone in reading order, so one merge-walk links the whole document in O(H + C).
# PURE: rows in, models out.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import ChunkIndexEntry, HeadingEntry

# ====== Local Project Imports ======
from .models import OutlineHeading


class OutlineBuilder:
    """Build outline headings (with page + section-opening chunk) from lean IR/chunk rows."""

    logger = loggerplusplus.bind(identifier="OutlineBuilder")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("OutlineBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(
        cls, headings: Sequence[HeadingEntry], chunks: Sequence[ChunkIndexEntry]
    ) -> list[OutlineHeading]:
        """
        Build the outline of a document.

        Args:
            headings (Sequence[HeadingEntry]): The heading blocks, in reading order.
            chunks (Sequence[ChunkIndexEntry]): The document's chunks, in chunk_index order.

        Returns:
            list[OutlineHeading]: One entry per non-empty heading, in reading order. A heading after
            the last chunk's end links nothing (``chunk_id`` None).
        """
        # 1. Only chunks placed in reading order can anchor a heading (a block-less chunk cannot).
        placed = [chunk for chunk in chunks if chunk.last_reading_order is not None]

        # 2. Merge-walk: advance the chunk cursor past every chunk that ends before the heading.
        outline: list[OutlineHeading] = []
        cursor = 0
        for heading in headings:
            text = heading.text.strip()
            if not text:
                continue
            while (
                cursor < len(placed) and placed[cursor].last_reading_order < heading.reading_order
            ):
                cursor += 1
            outline.append(
                OutlineHeading(
                    level=heading.level or 1,
                    text=text,
                    page_number=None if heading.page is None else heading.page + 1,
                    chunk_id=str(placed[cursor].id) if cursor < len(placed) else None,
                )
            )
        return outline


__all__ = ["OutlineBuilder"]
