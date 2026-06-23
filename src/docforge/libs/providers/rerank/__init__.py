# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all rerank providers (one folder per provider; bge = TEI cross-encoder
# with an editable locality flag, cohere = cloud API fixed external).
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import

auto_import(__name__)

# ─────────────────── Base ─────────────────────────────────────────── #
from .base import RerankProvider

# ─────────────────── Providers (one folder each) ───────────────────── #
from .bge import BgeRerankerConfig, BgeRerankProvider
from .cohere import CohereRerankConfig, CohereRerankProvider

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    "RerankProvider",
    "BgeRerankerConfig",
    "BgeRerankProvider",
    "CohereRerankConfig",
    "CohereRerankProvider",
]
