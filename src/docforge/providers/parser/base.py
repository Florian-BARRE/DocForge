# ====== Code Summary ======
# Abstract base class for all document parser backends.
# Every parser takes PDF bytes and produces a canonical DocumentIR.

from __future__ import annotations

from abc import ABC, abstractmethod

from ir.models import DocumentIR


class ParserProvider(ABC):
    """
    Abstract base class for all document parser backends.

    Parses a PDF into the canonical DocumentIR block tree.  Concrete
    implementations wrap third-party ML libraries (Docling, Marker, MinerU,
    Tika …) and translate their output to the shared schema.

    Heavy model loading should be deferred to the first parse() call
    (lazy initialisation) to avoid slow startup.

    Class attributes:
        name (str): Provider identifier used in logs and fingerprints.
        version (str): Parser engine version string.
        runs_on (str): Deployment location — "cpu", "gpu", or "remote".
    """

    name: str
    version: str
    runs_on: str

    @abstractmethod
    async def parse(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Parse PDF bytes into a canonical DocumentIR.

        CPU/GPU-bound work must be dispatched to a thread pool so the async
        event loop is never blocked.

        Args:
            pdf_bytes (bytes): PDF content to parse.
            doc_id (str): Document UUID written into the IR.
            source_hash (str): SHA-256 of the original file.

        Returns:
            DocumentIR: Fully populated intermediate representation.
        """
        ...
