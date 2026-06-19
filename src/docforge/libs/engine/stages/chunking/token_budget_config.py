# ====== Code Summary ======
# TokenBudgetConfig — typed config + build() for the token-budget intra-section split method.
# Registered into the "split_method" discriminated union via @register; the chunking
# __init__ imports params.py (which imports this module) so the decorator fires at import.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import TYPE_CHECKING, Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec

if TYPE_CHECKING:
    from libs.engine.stages.chunking.token_budget_splitter import TokenBudgetSplitter


@register("split_method")
class TokenBudgetConfig(BaseModel):
    """
    Token-budget intra-section split method.

    Config id: "token_budget" — no external infra required.
    Cuts a section when it exceeds max_tokens, optionally overlapping blocks.
    """

    _label: ClassVar[str] = "Token budget — fixed max_tokens per chunk (fast, always available)"

    id: Literal["token_budget"] = "token_budget"
    max_tokens: int = Field(default=512, ge=64, le=4096, description="Token budget per chunk before split.")
    overlap_blocks: int = Field(default=0, ge=0, le=8, description="Blocks repeated at the start of each split sub-chunk.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> TokenBudgetSplitter:
        """Instantiate TokenBudgetSplitter from this config."""
        from libs.engine.stages.chunking.token_budget_splitter import TokenBudgetSplitter
        return TokenBudgetSplitter(max_tokens=self.max_tokens, overlap_blocks=self.overlap_blocks)

    def merge_defaults(self, cfg: Any) -> TokenBudgetConfig:
        """Merge deployment defaults (CHUNK_MAX_TOKENS) into this config."""
        return self.model_copy(update={
            "max_tokens": self.max_tokens or getattr(cfg, "CHUNK_MAX_TOKENS", self.max_tokens),
            "overlap_blocks": self.overlap_blocks,
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Return availability status and description for this split method."""
        return True, "Fixed token budget · no external infra"


# ------------------- Public API ------------------- #
__all__ = ["TokenBudgetConfig"]
