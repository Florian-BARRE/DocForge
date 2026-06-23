# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all parser backends and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ParserProvider

# ------------------- Providers (one folder each) ------------------- #
from .docling import DoclingBackend, DoclingConfig

# ------------------- Discriminated Union ------------------- #
ParserConfig = build_union(get_configs("parser"))

# ------------------- Public API ------------------- #
__all__ = [
    "DoclingBackend",
    "DoclingConfig",
    "ParserConfig",
    "ParserProvider",
]
