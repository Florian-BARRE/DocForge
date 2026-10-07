# ====== Code Summary ======
# Lean, text-free read records behind the document-READING surface (outline + chunk context): a heading
# block reduced to what an outline shows, and a chunk reduced to what a neighbour walk and an outline link
# need (its order, searchability inputs, breadcrumb and where it ends in reading order). Neither carries
# chunk/block body text, so a whole-document scan stays cheap even on a 237k-character document.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HeadingEntry:
    """
    One HEADING block of a document's IR, reduced to its outline facts.

    Attributes:
        text (str): The heading text ('' when the parser stored none).
        level (int | None): The heading depth (1 = top level); None when the parser did not set one.
        page (int | None): 0-based page index; None for a page-less document (no real pages).
        reading_order (int): Position in the document's reading order.
    """

    text: str
    level: int | None
    page: int | None
    reading_order: int


@dataclass(frozen=True, slots=True)
class ChunkIndexEntry:
    """
    One chunk of a document, reduced to the facts a neighbour walk and an outline link need.

    Attributes:
        id (uuid.UUID): The chunk id.
        chunk_index (int): Position of the chunk within its document.
        role (str): The stored structural role (drives the default searchability).
        enabled_override (bool | None): The user's override (None = defer to the role default).
        heading_path (list[str]): The section breadcrumb, outer→inner ([] when none).
        last_reading_order (int | None): Highest reading order among the chunk's blocks — where the
            chunk ends in the document; None when the chunk has no block composition.
    """

    id: uuid.UUID
    chunk_index: int
    role: str
    enabled_override: bool | None
    heading_path: list[str]
    last_reading_order: int | None = None


__all__ = ["HeadingEntry", "ChunkIndexEntry"]
