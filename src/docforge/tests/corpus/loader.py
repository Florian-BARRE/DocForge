# ====== Code Summary ======
# Corpus loader — resolves the catalog to the committed files under documents/<fmt>/ and returns
# a CorpusManifest. Loading is read-only and deterministic: the documents are produced ONCE by
# tests/corpus/generation/ (modern formats) and tests/corpus/generation/legacy/ (legacy + PDF),
# then committed. A spec whose file is absent is skipped with a warning (e.g. legacy not yet baked),
# so the modern suite still runs.

# ====== Standard Library Imports ======
from __future__ import annotations

from pathlib import Path

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .catalog import CATALOG
from .manifest import CorpusManifest
from .spec import CorpusDocument, DocumentSpec

# Committed corpus lives next to this module under documents/<fmt>/<filename>.
CORPUS_ROOT: Path = Path(__file__).resolve().parent
DOCUMENTS_DIR: Path = CORPUS_ROOT / "documents"

_logger = loggerplusplus.bind(identifier="CorpusLoader")


def document_path(spec: DocumentSpec) -> Path:
    """
    Return the committed file path for a spec: documents/<fmt>/<filename>.

    Args:
        spec (DocumentSpec): The catalog spec.

    Returns:
        Path: Absolute path to the committed artifact.
    """
    return DOCUMENTS_DIR / spec.fmt / spec.filename


def load_corpus() -> CorpusManifest:
    """
    Load the committed corpus into a manifest.

    Returns:
        CorpusManifest: Every catalog document whose committed file exists.
    """
    # 1. Resolve each catalog spec to its committed file, skipping any that are missing
    documents: list[CorpusDocument] = []
    for spec in CATALOG:
        path = document_path(spec)
        if path.is_file():
            documents.append(CorpusDocument(spec=spec, path=path))
        else:
            _logger.warning(
                f"Corpus file missing for {spec.key!r}: {path} -- regenerate via "
                f"tests/corpus/generation (modern) or generation/legacy/bake_legacy.py (legacy)."
            )

    # 2. Return an immutable manifest
    _logger.debug(f"Loaded {len(documents)} corpus documents from {DOCUMENTS_DIR}.")
    return CorpusManifest(documents=tuple(documents))
