# ====== Code Summary ======
# CorpusGenerator — regenerates the COMMITTED modern documents (docx/xlsx/pptx/html/md) into
# tests/corpus/documents/<fmt>/. Run it ONCE (and after any builder change), then commit the
# refreshed files. Legacy binaries (.doc/.xls/.ppt) and the native .pdf are produced separately by
# generation/legacy/bake_legacy.py (they need LibreOffice). At test time the corpus is only LOADED
# (see corpus.loader), never generated — so test runs are deterministic.
#
# Usage (from src/docforge):
#   uv run python -m tests.corpus.generation.generator        # regenerate modern committed docs

# ====== Standard Library Imports ======
from __future__ import annotations

import sys
from pathlib import Path

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ─── Make the tests package importable when run as a module/script ────────────────
_DOCFORGE_ROOT = Path(__file__).resolve().parents[3]  # generator -> generation -> corpus -> tests -> docforge
if str(_DOCFORGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_DOCFORGE_ROOT))

# ====== Internal Project Imports ======
from tests.corpus.catalog import CATALOG, GENERATED_FORMATS
from tests.corpus.generation.natif import (
    DocxCorpusBuilder,
    HtmlCorpusBuilder,
    MarkdownCorpusBuilder,
    PptxCorpusBuilder,
    XlsxCorpusBuilder,
)
from tests.corpus.generation.natif.base import BaseDocumentBuilder
from tests.corpus.loader import DOCUMENTS_DIR

# Format -> builder class. One builder per generated (modern) format.
_BUILDERS: dict[str, type[BaseDocumentBuilder]] = {
    "docx": DocxCorpusBuilder,
    "xlsx": XlsxCorpusBuilder,
    "pptx": PptxCorpusBuilder,
    "html": HtmlCorpusBuilder,
    "md": MarkdownCorpusBuilder,
}


class CorpusGenerator(LoggerClass):
    """Regenerates the committed modern corpus documents under documents/<fmt>/."""

    def __init__(self, documents_dir: Path = DOCUMENTS_DIR) -> None:
        """
        Initialize the generator.

        Args:
            documents_dir (Path): Root of the committed corpus (documents/).
        """
        LoggerClass.__init__(self)
        self._documents_dir = documents_dir

    def regenerate(self) -> list[Path]:
        """
        (Re)build every modern-format catalog document and write it to documents/<fmt>/.

        Returns:
            list[Path]: The paths written.
        """
        # 1. Build each generated-format spec and write it under its extension folder
        written: list[Path] = []
        for spec in CATALOG:
            if spec.fmt not in GENERATED_FORMATS:
                continue
            data = _BUILDERS[spec.fmt](spec=spec).build()
            out = self._documents_dir / spec.fmt / spec.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            written.append(out)
            self.logger.info(
                f"Regenerated {spec.key} -> {out.relative_to(self._documents_dir)} ({len(data)} bytes)."
            )

        # 2. Remind that legacy/PDF are produced by the separate baker
        self.logger.info(
            f"Regenerated {len(written)} modern documents. Legacy (.doc/.xls/.ppt) and the native "
            f".pdf are produced by generation/legacy/bake_legacy.py."
        )
        return written


def main() -> int:
    """Regenerate the committed modern corpus documents."""
    CorpusGenerator().regenerate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
