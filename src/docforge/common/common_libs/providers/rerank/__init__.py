# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all rerank providers (one folder per provider; bge = TEI cross-encoder
# with an editable locality flag, cohere = cloud API fixed external).
# ─────────────────────────────────────────────────────────────────────────────

from common_libs.config.pipeline._registry import auto_import

auto_import(__name__)

# ─────────────────── Base ─────────────────────────────────────────── #
from .base import RerankProvider

# ─────────────────── Providers (one folder each) ───────────────────── #
# `bge_reranker` is no longer a registered rerank CHOICE (bge_server replaced the off-the-shelf TEI
# reranker image). The HTTP client BgeRerankProvider stays exported — it is the shared rerank client
# reused by BgeServerRerankConfig.build(). BgeRerankerConfig is exported only for backward-compat
# reference; being unregistered, it is absent from the rerank discriminated union.
from .bge import BgeRerankerConfig, BgeRerankProvider
from .bge_server import BgeServerRerankConfig
from .cohere import CohereRerankConfig, CohereRerankProvider

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    "RerankProvider",
    "BgeRerankerConfig",
    "BgeRerankProvider",
    "BgeServerRerankConfig",
    "CohereRerankConfig",
    "CohereRerankProvider",
]
