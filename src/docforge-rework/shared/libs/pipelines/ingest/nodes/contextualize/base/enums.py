# ====== Code Summary ======
# The shared knobs of the LLM-driven contextualization: the DOCUMENT SCOPE (what the model reads to
# situate a chunk — the cost/quality trade-off) and the per-chunk failure policy. They live in the
# family base because they are shared by the monolithic llm contextualizer AND the externalised
# prep node (both build the very same document view and honour the same failure stance).

# ====== Standard Library Imports ======
from enum import StrEnum


class DocumentScope(StrEnum):
    """What the model reads to situate a chunk — the cost/quality knob."""

    FULL = "full"        # the whole document text (best quality, costly on large docs)
    SECTION = "section"  # the chunk's section siblings (the balanced default)
    WINDOW = "window"    # ± window_chunks neighbours (cheapest)


class OnChunkError(StrEnum):
    """What a per-chunk model failure does."""

    KEEP_RAW = "keep_raw"  # the chunk passes through un-contextualised (logged)
    FAIL = "fail"          # the node fails (strict runs)


__all__ = ["DocumentScope", "OnChunkError"]
