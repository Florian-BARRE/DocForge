# ---------------------- dense_sparse embedder (the slot node) ---------------------- #
from .config import IN_STACK_BGE_URL, EmbedDenseSparseConfig
from .core import EmbedDenseSparseNode
from .legacy import DENSE_SPARSE_KIND, LEGACY_KINDS, EmbedLegacyMigration

# ------------------- Public API ------------------- #
__all__ = [
    "EmbedDenseSparseNode",
    "EmbedDenseSparseConfig",
    "IN_STACK_BGE_URL",
    "EmbedLegacyMigration",
    "DENSE_SPARSE_KIND",
    "LEGACY_KINDS",
]
