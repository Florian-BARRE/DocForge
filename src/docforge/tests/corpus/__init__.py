# ---------------------- Specs --------------------- #
from .spec import CorpusDocument, DocumentSpec
from .catalog import CATALOG, GENERATED_FORMATS, LEGACY_FORMATS
from .manifest import CorpusManifest

# -------------------- Loading --------------------- #
from .loader import CORPUS_ROOT, DOCUMENTS_DIR, document_path, load_corpus

# ------------------- Public API ------------------- #
__all__ = [
    "CorpusDocument",
    "DocumentSpec",
    "CorpusManifest",
    "CATALOG",
    "GENERATED_FORMATS",
    "LEGACY_FORMATS",
    "CORPUS_ROOT",
    "DOCUMENTS_DIR",
    "document_path",
    "load_corpus",
]
