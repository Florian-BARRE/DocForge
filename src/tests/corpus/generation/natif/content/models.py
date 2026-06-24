# ====== Code Summary ======
# ContentPack — a language- and type-specific bundle of realistic prose used to compose LONG,
# complex corpus documents. A pack supplies enough material (titles, a deep paragraph pool, contract
# clauses, lists, a wide table, footnote-style notes) that builders can repeat/cycle it into a
# multi-page document, stressing chunking, breadcrumb depth and language detection.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContentPack:
    """
    A reusable, single-language content bundle for one document archetype.

    Attributes:
        language (str): Language code ("fr" / "en" / "es") — the text is predominantly this language.
        title (str): Document title.
        subtitle (str): A one-line subtitle / reference shown under the title.
        searchable_phrase (str): A distinctive phrase guaranteed to appear in the body (search target).
        abstract (str): A distinctive opening paragraph.
        section_titles (list[str]): Pool of heading texts (cycled to build many sections).
        paragraphs (list[str]): Pool of substantial paragraphs (cycled to reach real length).
        clauses (list[str]): Contract clause bodies (cycled into numbered articles).
        list_items (list[str]): Items for multi-level lists.
        table_caption (str): Caption for the wide (landscape) table.
        table_headers (list[str]): Column headers of the wide table.
        table_rows (list[list[str]]): Data rows of the wide table.
        notes (list[str]): Footnote / endnote style remarks.
        column_blurb (str): A long paragraph rendered in a multi-column section.
    """

    language: str
    title: str
    subtitle: str
    searchable_phrase: str
    abstract: str
    section_titles: list[str]
    paragraphs: list[str]
    clauses: list[str] = field(default_factory=list)
    list_items: list[str] = field(default_factory=list)
    table_caption: str = ""
    table_headers: list[str] = field(default_factory=list)
    table_rows: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    column_blurb: str = ""

    def para(self, i: int) -> str:
        """Return paragraph i, cycling through the pool so builders can produce many sections."""
        return self.paragraphs[i % len(self.paragraphs)]

    def section_title(self, i: int) -> str:
        """Return section title i, cycling through the pool."""
        return self.section_titles[i % len(self.section_titles)]

    def clause(self, i: int) -> str:
        """Return clause i, cycling through the pool (falls back to paragraphs if empty)."""
        pool = self.clauses or self.paragraphs
        return pool[i % len(pool)]
