# ====== Code Summary ======
# BaseDocumentBuilder — abstract base for every format builder. A builder turns a
# DocumentSpec (+ a unique run marker) into the raw bytes of one synthetic document.
# Subclasses implement build(); the marker is woven into the content so each generated
# file has a distinct source_hash and search can pinpoint it.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from ...spec import DocumentSpec


class BaseDocumentBuilder(ABC, LoggerClass):
    """
    Abstract base for synthetic document builders.

    Each concrete builder produces a genuinely hard document for its format: deep heading
    hierarchies, multi-row tables, embedded raster figures, captions, lists, accented
    unicode and multiple pages — so the ingestion pipeline exercises real code paths.
    """

    def __init__(self, spec: DocumentSpec, marker: str | None = None) -> None:
        """
        Initialize the builder.

        Args:
            spec (DocumentSpec): What the document must contain.
            marker (str | None): Token embedded in the content for traceability; defaults to the
                stable spec key so regenerated committed documents are deterministic.
        """
        LoggerClass.__init__(self)
        self.spec = spec
        self.marker = marker or spec.key

    @abstractmethod
    def build(self) -> bytes:
        """
        Build the document and return its raw bytes.

        Returns:
            bytes: The encoded document, ready to be written to disk or uploaded.
        """
        ...

    # ─── Shared content helpers ──────────────────────────────────────────────────

    def _intro(self) -> str:
        """Return the standard intro sentence carrying the unique marker + searchable phrase."""
        return (
            f"Identifiant unique de ce document de test : {self.marker}. "
            f"{self.spec.searchable_phrase} "
            "Ce corpus synthétique éprouve la conversion, le parsing et l'indexation."
        )

    @staticmethod
    def _lorem(n: int = 3) -> str:
        """
        Return a block of accented filler prose long enough to force chunking.

        Args:
            n (int): Number of sentences to emit.
        """
        sentence = (
            "L'évaluation des risques opérationnels repose sur des contrôles réguliers, "
            "une gouvernance claire et une piste d'audit traçable de bout en bout. "
        )
        return (sentence * n).strip()
