# ====== Code Summary ======
# SentenceWindowConfig — typed config + build() for the sentence-window intra-section split
# method.  Registered into the "split_method" discriminated union via @register; the chunking
# __init__ imports params.py (which imports this module) so the decorator fires at import.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import TYPE_CHECKING, Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

if TYPE_CHECKING:
    from common_libs.pipeline.stages.s4_chunk.strategies.sentence_window import SentenceWindowSplitter


@register("split_method")
class SentenceWindowConfig(BaseModel):
    """
    Sentence-window intra-section split method.

    Config id: "sentence_window" — no external infra required.
    Slides a fixed window of sentences with a configurable stride.
    """

    _label: ClassVar[str] = "Sentence window — sliding window of sentences (fast, always available)"

    id: Literal["sentence_window"] = "sentence_window"
    window_sentences: int = Field(default=5, ge=1, le=50, description="Sentences per window.")
    stride_sentences: int = Field(default=4, ge=1, le=50, description="Sentences advanced between windows.")
    max_tokens: int = Field(default=512, ge=64, le=4096, description="Packing reference for small sections.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> SentenceWindowSplitter:
        """Instantiate SentenceWindowSplitter from this config."""
        from common_libs.pipeline.stages.s4_chunk.strategies.sentence_window import SentenceWindowSplitter
        return SentenceWindowSplitter(
            window_sentences=self.window_sentences,
            stride_sentences=self.stride_sentences,
            max_tokens=self.max_tokens,
        )

    def merge_defaults(self, cfg: Any) -> SentenceWindowConfig:
        """No deployment defaults to merge for the sentence-window method."""
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Return availability status and description for this split method."""
        return True, "Sliding sentence window · no external infra"


# ------------------- Public API ------------------- #
__all__ = ["SentenceWindowConfig"]
