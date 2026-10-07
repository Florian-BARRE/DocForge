# ====== Code Summary ======
# ChunkWindow — picks the context window around one chunk: up to ``before`` enabled chunks preceding
# it and up to ``after`` following it, by chunk_index within the same document. Disabled neighbours
# (header/footer, TOC, boilerplate, user-hidden) are skipped and the window reaches past them; the
# target itself is always kept, whatever its own state. PURE: lean rows in, ordered rows out.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import ChunkIndexEntry

# ====== Local Project Imports ======
from .chunk_enablement import ChunkEnablement


class ChunkWindow:
    """Select a chunk's enabled neighbours by chunk_index."""

    logger = loggerplusplus.bind(identifier="ChunkWindow")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChunkWindow is a static-only class and cannot be instantiated.")

    @staticmethod
    def _enabled(entry: ChunkIndexEntry) -> bool:
        """Whether a neighbour may enter the window (its effective searchability)."""
        return ChunkEnablement.effective(entry.role, entry.enabled_override, entry.id)

    @classmethod
    def select(
        cls, entries: Sequence[ChunkIndexEntry], target_id: uuid.UUID, before: int, after: int
    ) -> list[ChunkIndexEntry]:
        """
        Return the window around ``target_id`` in chunk_index order (target included).

        Args:
            entries (Sequence[ChunkIndexEntry]): The document's chunks, in chunk_index order.
            target_id (uuid.UUID): The chunk the window is centred on.
            before (int): How many enabled chunks to take before the target.
            after (int): How many enabled chunks to take after the target.

        Returns:
            list[ChunkIndexEntry]: The window, ordered; [] when the target is not among ``entries``.
        """
        # 1. Locate the target in the ordered index.
        position = next((i for i, entry in enumerate(entries) if entry.id == target_id), None)
        if position is None:
            return []

        # 2. Walk outwards on each side, keeping only enabled neighbours up to the requested count.
        preceding = [entry for entry in reversed(entries[:position]) if cls._enabled(entry)][
            :before
        ]
        following = [entry for entry in entries[position + 1 :] if cls._enabled(entry)][:after]

        # 3. Reassemble in chunk_index order around the target.
        return [*reversed(preceding), entries[position], *following]


__all__ = ["ChunkWindow"]
