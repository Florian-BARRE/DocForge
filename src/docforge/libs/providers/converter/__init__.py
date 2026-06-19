# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all converter providers and build the discriminated union.
# Adding a new converter = create a file, annotate @register("converter"), done.
# ─────────────────────────────────────────────────────────────────────────────

# ---------------------- Auto-discovery ---------------------- #
from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)  # imports local/ and external/ — triggers @register decorators

# ---------------------- Base ---------------------- #
from .base import ConverterProvider

# ------------------- Local Providers ------------------- #
from .local.gotenberg import (
    GOTENBERG_FORMATS,
    NATIVE_PDF_FORMATS,
    GotenbergConverter,
)
from .local.gotenberg_config import GotenbergConfig

# ------------------- Discriminated Union ------------------- #
# Built dynamically from all registered converter configs.
ConverterConfig = build_union(get_configs("converter"))

# ------------------- Public API ------------------- #
__all__ = [
    "ConverterConfig",
    "ConverterProvider",
    "GotenbergConfig",
    "GotenbergConverter",
    "GOTENBERG_FORMATS",
    "NATIVE_PDF_FORMATS",
]
