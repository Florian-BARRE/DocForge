# ====== Code Summary ======
# ParserProvider Protocol — defines the interface for PDF-to-IR parsing backends
# (DoclingBackend, MinerUBackend, MarkerBackend). Each adapter translates backend-specific
# output into the canonical DocumentIR schema.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and IR type only)
# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR

# ====== Local Project Imports ======
# (none)


@runtime_checkable
class ParserProvider(Protocol):
    """
    Parses a PDF (or natively-supported format) into a DocumentIR.

    Implementations: DoclingBackend, MinerUBackend, MarkerBackend.
    Each adapter translates backend-specific output → the canonical DocumentIR schema.
    """

    name: str
    version: str
    runs_on: str  # "cpu" | "gpu" | "remote"

    async def parse(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Parse PDF bytes into a DocumentIR.

        Args:
            pdf_bytes (bytes): PDF content to parse.
            doc_id (str): Document UUID (written into the IR).
            source_hash (str): SHA-256 of the original file (written into the IR).

        Returns:
            DocumentIR: Fully populated intermediate representation.
        """
        ...
