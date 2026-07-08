# ====== Code Summary ======
# ContextualizerLlmPrepConfig — the config of the llm contextualize PREP node, which doubles as the
# contextualize LLM STAGE config the studio edits. It carries everything the prep needs to SHAPE the
# situating prompts it emits (the situating instruction and the DOCUMENT SCOPE rules that decide what
# each chunk's view contains) PLUS the two STAGE-EXECUTION knobs — ``max_concurrency`` and
# ``on_error`` — that became graph mechanics once the model call was externalised into an llm chain.
# Those two are NOT consumed by the prep's run(): they are read by the stage assembler to shape the
# ForEach the prep is wrapped in (its concurrency) and the fail-soft keep_raw terminal of its body
# (the on_error edge). The endpoint + generation params do NOT live here — they moved to the llm
# chain steps the ForEach body runs.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from ..base import DEFAULT_SITUATE_PROMPT, BaseContextualizerConfig, DocumentScope, OnChunkError


class ContextualizerLlmPrepConfig(BaseContextualizerConfig):
    """The situating instruction + document-scope rules, plus the two stage-execution knobs."""

    system_prompt: str = Field(
        default=DEFAULT_SITUATE_PROMPT,
        description="The situating instruction (the model's answer becomes the chunk's context piece).",
    )
    document_scope: DocumentScope = Field(
        default=DocumentScope.SECTION,
        description="What the model reads: full document / the chunk's section (falls back to "
        "window when the chunk has no section) / ± window_chunks neighbours.",
    )
    window_chunks: int = Field(
        default=2, ge=1,
        description="Neighbours on each side for the window scope (and the section fallback).",
    )
    max_document_words: int = Field(
        default=4000, gt=0,
        description="Hard cap on the document text handed to the model (truncated from the "
        "start, where documents introduce themselves).",
    )
    max_concurrency: int = Field(
        default=4, ge=1,
        description="Stage knob (read by the assembler): how many prompts the ForEach runs at once.",
    )
    on_error: OnChunkError = Field(
        default=OnChunkError.KEEP_RAW,
        description="Stage knob (read by the assembler): keep_raw wires a fail-soft terminal so a "
        "failed chunk stays raw; fail lets the failure propagate as an item failure.",
    )


__all__ = ["ContextualizerLlmPrepConfig"]
