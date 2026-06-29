# -------------------- Native ingest stages --------------------- #
# Importing the native stages here is the registration backstop: it forces each stage's
# @register_stage to fire on ``import common_libs.pipeline.ingest.stages`` even before
# auto_import_stages() walks the package. All seven ingest stages are now native (the adapters
# package is gone).
from .chunk import ChunkStage
from .contextualize import ContextualizeStage
from .embed_index import EmbedIndexStage
from .enrich import EnrichStage
from .ingest import IngestDocStage
from .metagen import MetagenStage
from .parsing import ParsingStage

# -------------------- Public API ------------------------------- #
__all__ = [
    "IngestDocStage",
    "ParsingStage",
    "EnrichStage",
    "ChunkStage",
    "ContextualizeStage",
    "MetagenStage",
    "EmbedIndexStage",
]
