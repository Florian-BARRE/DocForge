# ====== Code Summary ======
# Config of the llm contextualizer — Anthropic-style contextual retrieval: an LLM writes
# a short situating snippet per chunk. The DOCUMENT SCOPE decides what the model reads to situate
# the chunk (cost/quality trade-off), with explicit fallback rules; degradation policy decides
# what a per-chunk failure does.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig

# ====== Local Project Imports ======
from ..base import BaseContextualizerConfig

# The Anthropic contextual-retrieval instruction: answer with the situating snippet, nothing else.
DEFAULT_SITUATE_PROMPT = (
    "You situate a chunk within its source document to improve search retrieval. "
    "Given the document content and one chunk of it, answer ONLY with 1-2 short sentences "
    "stating what the chunk is about and where it belongs in the document. No preamble."
)


class DocumentScope(StrEnum):
    """What the model reads to situate a chunk — the cost/quality knob."""

    FULL = "full"        # the whole document text (best quality, costly on large docs)
    SECTION = "section"  # the chunk's section siblings (the balanced default)
    WINDOW = "window"    # ± window_chunks neighbours (cheapest)


class OnChunkError(StrEnum):
    """What a per-chunk model failure does."""

    KEEP_RAW = "keep_raw"  # the chunk passes through un-contextualised (logged)
    FAIL = "fail"          # the node fails (strict runs)


class ContextualizerLlmConfig(BaseContextualizerConfig, OpenAICompatConfig):
    """Generation + scope rules of the situating model (endpoint fields inherited)."""

    model: str = Field(description="Model used to situate the chunks.")
    system_prompt: str = Field(
        default=DEFAULT_SITUATE_PROMPT,
        description="The situating instruction (the answer becomes the chunk's context piece).",
    )
    max_tokens: int = Field(default=120, gt=0, description="Generation cap for the situating snippet.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    document_scope: DocumentScope = Field(
        default=DocumentScope.SECTION,
        description="What the model reads: full document / the chunk's section (falls back to "
        "window when the chunk has no section) / ± window_chunks neighbours.",
    )
    window_chunks: int = Field(
        default=2, ge=1, description="Neighbours on each side for the window scope (and the "
        "section fallback)."
    )
    max_document_words: int = Field(
        default=4000,
        gt=0,
        description="Hard cap on the document text handed to the model (truncated from the "
        "start, where documents introduce themselves).",
    )
    max_concurrency: int = Field(
        default=4, ge=1, description="Simultaneous model calls (internal bound)."
    )
    on_error: OnChunkError = Field(
        default=OnChunkError.KEEP_RAW,
        description="Per-chunk failure policy: keep the chunk raw (default) or fail the node.",
    )


__all__ = [
    "ContextualizerLlmConfig",
    "DocumentScope",
    "OnChunkError",
    "DEFAULT_SITUATE_PROMPT",
]
