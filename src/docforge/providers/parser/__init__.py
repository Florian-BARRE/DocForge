# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all parser backends and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from providers._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ParserProvider

# ------------------- Local Providers ------------------- #
from .local.docling import DoclingConfig, DoclingBackend

# ------------------- Discriminated Union ------------------- #
ParserConfig = build_union(get_configs("parser"))

# ------------------- Public API ------------------- #
__all__ = [
    "DoclingBackend",
    "DoclingConfig",
    "ParserConfig",
    "ParserProvider",
]
