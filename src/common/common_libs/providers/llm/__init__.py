# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all LLM providers (one folder per provider; local vs external is a
# `locality` flag on the unified openai_compat config, not a separate class).
# ─────────────────────────────────────────────────────────────────────────────

from common_libs.config.pipeline._registry import auto_import

auto_import(__name__)

# ─────────────────── Base ─────────────────────────────────────────── #
from .base import LLMProvider

# ─────────────────── Providers (one folder each) ───────────────────── #
from .openai_compat import OpenAICompatLLMConfig, OpenAICompatLLMProvider

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    "LLMProvider",
    "OpenAICompatLLMConfig",
    "OpenAICompatLLMProvider",
]
