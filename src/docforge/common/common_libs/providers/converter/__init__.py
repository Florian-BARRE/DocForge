# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all converter providers and build the discriminated union.
# Adding a new converter = create a file, annotate @register("converter"), done.
# ─────────────────────────────────────────────────────────────────────────────

# ---------------------- Standard Library ---------------------- #
import importlib

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

# ------------------- Runtime re-exports (lazy) ------------------- #
# Runtime implementations (and their module-level format constants) are re-exported lazily
# (PEP 562) so importing this package for config auto-discovery never eagerly pulls the heavy
# runtime dependency (e.g. PyMuPDF) into the lightweight app image. Each name is imported only
# when first accessed (typically inside GotenbergConfig.build()), preserving the config/runtime
# layering.
_RUNTIME_EXPORTS = {
    "GotenbergConverter": (".gotenberg.provider", "GotenbergConverter"),
    "GOTENBERG_FORMATS": (".gotenberg.provider", "GOTENBERG_FORMATS"),
    "NATIVE_PDF_FORMATS": (".gotenberg.provider", "NATIVE_PDF_FORMATS"),
}


def __getattr__(name: str):
    """Lazily import and return a runtime symbol re-exported by this package."""
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    return getattr(module, target[1])


# ------------------- Public API ------------------- #
__all__ = [
    "GOTENBERG_FORMATS",
    "GotenbergConfig",
    "GotenbergConverter",
    "ConverterConfig",
    "ConverterProvider",
    "NATIVE_PDF_FORMATS",
]
