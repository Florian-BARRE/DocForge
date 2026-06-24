# ====== Code Summary ======
# MarkdownCorpusBuilder — authors a rich CommonMark document (headings, table, lists, code
# block, blockquote, accented unicode). DocForge does NOT accept .md as an ingest format
# (only pdf + the Gotenberg office/html/txt set), so this artifact drives the 415
# unsupported-format negative test while still representing the "markdown" format requested.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from .base import BaseDocumentBuilder


class MarkdownCorpusBuilder(BaseDocumentBuilder):
    """Builds a rich Markdown document used as the unsupported-format (415) negative fixture."""

    def build(self) -> bytes:
        """
        Assemble the Markdown document and return its UTF-8 bytes.

        Returns:
            bytes: A valid, rich .md document.
        """
        # 1. Compose focused fragments into one CommonMark document
        parts = [
            f"# {self.spec.title}",
            "",
            f"> {self._intro()}",
            "",
            "## 1. Contexte",
            "",
            self._lorem(4),
            "",
            "### 1.1 Méthodologie",
            "",
            self._lorem(3),
            "",
            self.__table(),
            "",
            self.__lists(),
            "",
            self.__code_block(),
            "",
        ]
        # 2. Join with newlines and encode
        return "\n".join(parts).encode("utf-8")

    @staticmethod
    def __table() -> str:
        """Return a GitHub-flavoured Markdown table."""
        return (
            "| Indicateur | T1 2026 | T2 2026 |\n"
            "|---|---:|---:|\n"
            "| Chiffre d'affaires | 1 240 k€ | 1 530 k€ |\n"
            "| Marge brute | 38 % | 41 % |\n"
            "| Incidents critiques | 2 | 0 |"
        )

    @staticmethod
    def __lists() -> str:
        """Return a bulleted list and a numbered list."""
        return (
            "## 2. Recommandations\n\n"
            "- Renforcer la traçabilité\n"
            "- Automatiser les contrôles\n\n"
            "1. Cadrage\n"
            "2. Réalisation\n"
            "3. Recette"
        )

    @staticmethod
    def __code_block() -> str:
        """Return a fenced code block."""
        return "```python\ndef score(chunks: list[str]) -> float:\n    return len(chunks) / 10.0\n```"
