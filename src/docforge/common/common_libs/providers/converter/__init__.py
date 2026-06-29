# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all converter providers and build the discriminated union.
# Adding a new converter = create a file, annotate @register("converter"), done.
# ─────────────────────────────────────────────────────────────────────────────

# ---------------------- Auto-discovery ---------------------- #
from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)  # imports each provider folder — triggers @register decorators

# ---------------------- Base ---------------------- #
from .base import ConverterProvider

# ------------------- Providers (one folder each) ------------------- #
from .gotenberg import GotenbergConfig

# ------------------- Discriminated Union ------------------- #
# Built dynamically from all registered converter configs.
ConverterConfig = build_union(get_configs("converter"))

# ------------------- Public API ------------------- #
__all__ = [
    "ConverterConfig",
    "ConverterProvider",
    "GotenbergConfig",
]
