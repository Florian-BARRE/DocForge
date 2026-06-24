# ====== Code Summary ======
# Declarative specs for the test corpus. A DocumentSpec describes WHAT a corpus document contains
# and the MINIMUM structure the pipeline must recover (figures/tables/headings/pages/chunks). A
# CorpusDocument binds a spec to its committed file under documents/<fmt>/. Assertions are
# minimum-based because Gotenberg -> Docling conversion is lossy, never an exact round-trip.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentSpec:
    """
    Static description of one corpus document.

    Attributes:
        key (str): Stable identifier (e.g. "rich_docx") tests look the document up by.
        fmt (str): File extension without the dot (e.g. "docx") — also its documents/<fmt>/ folder.
        filename (str): Upload filename, including extension.
        title (str): Document title — embedded so search can target it.
        searchable_phrase (str): A distinctive phrase guaranteed to appear in the body, used by
            search tests to assert the document is retrievable.
        ingestable (bool): True when DocForge accepts this format (drives happy-path vs negative).
        min_pages (int): Minimum page count expected after conversion.
        min_figures (int): Minimum number of FIGURE blocks expected across all pages.
        min_tables (int): Minimum number of TABLE blocks expected across all pages.
        min_headings (int): Minimum number of distinct heading levels authored.
        min_chunks (int): Minimum number of retrieval chunks expected.
        doc_type (str): Content archetype the builder composes ("contract", "report", "data",
            "deck", "note"). Drives which content pack + layout the builder uses.
        language (str): Authoring language code ("fr" / "en" / "es" / "") — selects the content pack.
        expected_language (str | None): Language the pipeline should DETECT (usually == language);
            None disables the language-detection assertion for this document.
        source_key (str | None): For baked documents (legacy / native PDF), the key of the generated
            document this one is converted FROM.
        description (str): Human-readable summary of the traps this document exercises.
    """

    key: str
    fmt: str
    filename: str
    title: str
    searchable_phrase: str
    ingestable: bool = True
    min_pages: int = 1
    min_figures: int = 0
    min_tables: int = 0
    min_headings: int = 0
    min_chunks: int = 1
    doc_type: str = ""
    language: str = ""
    expected_language: str | None = None
    source_key: str | None = None
    description: str = ""


@dataclass(frozen=True)
class CorpusDocument:
    """
    A committed corpus artifact: its spec + the file under documents/<fmt>/.

    Attributes:
        spec (DocumentSpec): The declarative spec this artifact was built from.
        path (Path): Absolute path to the committed file in documents/<fmt>/.
    """

    spec: DocumentSpec
    path: Path

    @property
    def key(self) -> str:
        """Return the document's stable identifier."""
        return self.spec.key

    @property
    def fmt(self) -> str:
        """Return the document's format extension (no dot)."""
        return self.spec.fmt

    @property
    def filename(self) -> str:
        """Return the upload filename for this document."""
        return self.spec.filename

    def read_bytes(self) -> bytes:
        """
        Read the raw file bytes from disk.

        Returns:
            bytes: The full file content.

        Raises:
            FileNotFoundError: If the committed artifact is missing (run the generator/baker).
        """
        # 1. Fail loudly if the artifact is missing — a silent empty upload would mask the bug
        if not self.path.is_file():
            raise FileNotFoundError(f"Corpus artifact missing: {self.path}")
        # 2. Return the full content
        return self.path.read_bytes()
