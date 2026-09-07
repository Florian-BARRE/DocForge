# ---------------------- I/O contract ---------------------- #
from .io import ParserConsumes, ParserProduces

# ---------------------- Abstract base node ---------------------- #
from .node import BaseParserNode

# ---------------------- Shared post-passes ---------------------- #
from .helpers import BaseParserHelpers

# ------------------- Public API ------------------- #
# NOTE: LanguageDetector moved to shared_libs.pipelines.ingest.nodes.docmeta.language.detector —
# language detection is now a dedicated, visible graph node, no longer a parser side-effect.
__all__ = [
    "ParserConsumes",
    "ParserProduces",
    "BaseParserNode",
    "BaseParserHelpers",
]
