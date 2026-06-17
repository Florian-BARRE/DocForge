# ====== Code Summary ======
# Typed config+build() models for each intra-section split method.
# Each class is a Pydantic discriminated-union member: id: Literal[...] selects the method,
# typed params replace the old free-form dict, and build() instantiates the splitter.
# The SPLIT_METHOD_PARAMS catalog still maps id → model for describe_stages() schema derivation.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, model_validator


def _flatten_provider_spec(v: Any) -> Any:
    """Backward compat: accept old ProviderSpec {id, params} format."""
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


from typing import ClassVar
from providers._registry import register


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

    def build(self) -> "TokenBudgetSplitter":
        """Instantiate TokenBudgetSplitter from this config."""
        from pipeline.stages.chunking.token_budget_splitter import TokenBudgetSplitter
        return TokenBudgetSplitter(max_tokens=self.max_tokens, overlap_blocks=self.overlap_blocks)

    def merge_defaults(self, cfg: Any) -> "TokenBudgetConfig":
        return self.model_copy(update={
            "max_tokens": self.max_tokens or getattr(cfg, "CHUNK_MAX_TOKENS", self.max_tokens),
            "overlap_blocks": self.overlap_blocks,
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Return availability status and description for this split method."""
        return True, "Fixed token budget · no external infra"


@register("split_method")
class SemanticConfig(BaseModel):
    """
    Semantic (embedding-based) intra-section split method.

    Config id: "semantic" — requires a reachable TEI embedding endpoint.
    Places boundaries at points of maximum semantic distance between sentences.
    """

    _label: ClassVar[str] = "Semantic — embedding-based boundary detection (requires TEI)"

    id: Literal["semantic"] = "semantic"
    base_url: str = Field(default="", description="TEI endpoint (defaults to deployment TEI when empty).")
    max_tokens: int = Field(default=512, ge=64, le=4096, description="Hard cap per piece.")
    min_tokens: int = Field(default=128, ge=0, le=2048, description="Minimum size before a semantic cut is honoured.")
    breakpoint_percentile: int = Field(default=90, ge=50, le=99, description="Distance percentile above which a boundary is placed.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> "SemanticSplitter":
        """Instantiate SemanticSplitter with a TeiEmbedProvider for boundary detection."""
        from pipeline.stages.chunking.semantic_splitter import SemanticSplitter
        from providers.embed.local.tei import TeiEmbedProvider
        embed = TeiEmbedProvider(
            base_url=self.base_url,
            batch_size=32,
            embed_sparse=False,  # Dense only — boundary detection doesn't use sparse
        )
        return SemanticSplitter(
            embed_provider=embed,
            max_tokens=self.max_tokens,
            min_tokens=self.min_tokens,
            breakpoint_percentile=self.breakpoint_percentile,
        )

    def merge_defaults(self, cfg: Any) -> "SemanticConfig":
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "TEI_BASE_URL", ""),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Return availability status and description for this split method."""
        import socket
        from urllib.parse import urlparse
        base_url = getattr(cfg, "TEI_BASE_URL", "http://tei:8080")
        try:
            p = urlparse(base_url)
            with socket.create_connection((p.hostname or "tei", p.port or 8080), timeout=1):
                return True, f"Semantic boundaries via TEI · {base_url}"
        except OSError:
            return False, f"Requires TEI server at {base_url}"


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

    def build(self) -> "SentenceWindowSplitter":
        """Instantiate SentenceWindowSplitter from this config."""
        from pipeline.stages.chunking.sentence_window_splitter import SentenceWindowSplitter
        return SentenceWindowSplitter(
            window_sentences=self.window_sentences,
            stride_sentences=self.stride_sentences,
            max_tokens=self.max_tokens,
        )

    def merge_defaults(self, cfg: Any) -> "SentenceWindowConfig":
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Return availability status and description for this split method."""
        return True, "Sliding sentence window · no external infra"


# Backward-compat aliases (old name → new name)
TokenBudgetParams = TokenBudgetConfig
SemanticParams = SemanticConfig
SentenceWindowParams = SentenceWindowConfig

# Source-of-truth catalog: split method id → its config model.
# derive_stages(), registry builder, and docs all derive from this.
SPLIT_METHOD_PARAMS: dict[str, type[BaseModel]] = {
    "token_budget": TokenBudgetConfig,
    "semantic": SemanticConfig,
    "sentence_window": SentenceWindowConfig,
}
