# ====== Code Summary ======
# CorpusManifest — an immutable view over the built corpus. Provides ergonomic lookups used
# throughout the live suite: by key, by format, and partitioned into ingestable (happy path)
# vs non-ingestable (415 negatives) documents.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass

# ====== Local Project Imports ======
from .spec import CorpusDocument


@dataclass(frozen=True)
class CorpusManifest:
    """
    Immutable collection of built corpus documents with convenience lookups.

    Attributes:
        documents (tuple[CorpusDocument, ...]): Every successfully built/loaded artifact.
    """

    documents: tuple[CorpusDocument, ...]

    def get(self, key: str) -> CorpusDocument:
        """
        Return the document with the given key.

        Args:
            key (str): The document's stable identifier.

        Returns:
            CorpusDocument: The matching artifact.

        Raises:
            KeyError: If no document has that key.
        """
        # 1. Linear scan — the corpus is small (single digits)
        for doc in self.documents:
            if doc.key == key:
                return doc
        raise KeyError(f"No corpus document with key {key!r}.")

    def by_format(self, fmt: str) -> CorpusDocument:
        """Return the first document of the given format extension."""
        for doc in self.documents:
            if doc.fmt == fmt:
                return doc
        raise KeyError(f"No corpus document with format {fmt!r}.")

    @property
    def ingestable(self) -> tuple[CorpusDocument, ...]:
        """Documents in a format DocForge accepts (happy-path ingestion)."""
        return tuple(d for d in self.documents if d.spec.ingestable)

    @property
    def negatives(self) -> tuple[CorpusDocument, ...]:
        """Documents in an unsupported format (drive 415 negative tests)."""
        return tuple(d for d in self.documents if not d.spec.ingestable)

    @property
    def all_formats(self) -> tuple[str, ...]:
        """Every format extension present in the manifest."""
        return tuple(d.fmt for d in self.documents)
