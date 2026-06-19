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
from libs.core.contracts._registry import register


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
        from libs.engine.stages.chunking.token_budget_splitter import TokenBudgetSplitter
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

    Config id: "semantic" — requires ANY embed provider reachable at build time.
    Places boundaries at points of maximum semantic distance between sentences.

    The embed provider is a fully typed discriminated union (TEI / openai_compat / openai),
    identical to the one used by S6 — so semantic chunking and indexing can share or
    differ at will (e.g. a cheap local embed for boundary detection + a cloud embed for
    retrieval-quality vectors at index time).

    Backward-compat: a legacy ``{base_url: "..."}`` flat config is lifted to
    ``{embed: {id: "tei", base_url: "..."}}`` so old DB rows still load.
    """

    _label: ClassVar[str] = "Semantic — embedding-based boundary detection (any embed provider)"

    id: Literal["semantic"] = "semantic"
    embed: Any = Field(
        default=None,
        description=(
            "Embed provider used for boundary detection — typed EmbedProviderConfig "
            "(TeiEmbedConfig / LocalOpenAIEmbedConfig / OpenAIEmbedConfig).  None = "
            "default TEI when the config is materialised."
        ),
    )
    max_tokens: int = Field(default=512, ge=64, le=4096, description="Hard cap per piece.")
    min_tokens: int = Field(default=128, ge=0, le=2048, description="Minimum size before a semantic cut is honoured.")
    breakpoint_percentile: int = Field(default=90, ge=50, le=99, description="Distance percentile above which a boundary is placed.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """
        Accept both new ``{embed: {...}}`` and legacy ``{base_url: "..."}`` shapes.

        The legacy shape is lifted to a TEI embed config so old DB rows keep loading.
        """
        v = _flatten_provider_spec(v)
        if isinstance(v, dict):
            v = dict(v)
            # Legacy: top-level base_url meant TEI
            if "embed" not in v and "base_url" in v:
                v["embed"] = {"id": "tei", "base_url": v.pop("base_url")}
            # Flatten nested {id, params} on the embed sub-config
            if isinstance(v.get("embed"), dict):
                v["embed"] = _flatten_provider_spec(v["embed"])
        return v

    @model_validator(mode="after")
    def _validate_embed(self) -> "SemanticConfig":
        """Coerce ``embed`` into a typed EmbedProviderConfig instance after construction."""
        # Lazy import — avoids a circular import at module load time.
        from libs.capabilities.embed import EmbedProviderConfig  # noqa: F401  (typing alias)
        from libs.capabilities.embed.local.tei import TeiEmbedConfig
        from libs.capabilities.embed.local.openai_compat import LocalOpenAIEmbedConfig
        from libs.capabilities.embed.external.openai_compat import OpenAIEmbedConfig
        from pydantic import TypeAdapter
        from typing import Annotated, Union
        from pydantic import Field as _F

        # Default to TEI when the field is None (e.g. legacy DB row without embed key).
        if self.embed is None:
            object.__setattr__(self, "embed", TeiEmbedConfig())
            return self

        # Already a typed instance — nothing to do.
        if isinstance(self.embed, (TeiEmbedConfig, LocalOpenAIEmbedConfig, OpenAIEmbedConfig)):
            return self

        # Dict → validate via the same discriminated union the rest of the codebase uses.
        Union_ = Annotated[
            Union[TeiEmbedConfig, LocalOpenAIEmbedConfig, OpenAIEmbedConfig],
            _F(discriminator="id"),
        ]
        adapter = TypeAdapter(Union_)
        object.__setattr__(self, "embed", adapter.validate_python(self.embed))
        return self

    def build(self) -> "SemanticSplitter":
        """Instantiate SemanticSplitter with the configured embed provider."""
        from libs.engine.stages.chunking.semantic_splitter import SemanticSplitter
        embed_provider = self.embed.build()
        return SemanticSplitter(
            embed_provider=embed_provider,
            max_tokens=self.max_tokens,
            min_tokens=self.min_tokens,
            breakpoint_percentile=self.breakpoint_percentile,
        )

    def merge_defaults(self, cfg: Any) -> "SemanticConfig":
        """Merge deployment defaults into the nested embed config."""
        merged_embed = self.embed.merge_defaults(cfg) if self.embed is not None else None
        return self.model_copy(update={"embed": merged_embed})

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Report availability of the DEFAULT semantic config (TEI on the deployment env vars).

        At the per-collection level, the user picks any embed provider — its own
        availability is reported under the embed picker.  This classmethod only describes
        the heuristic "is the deployment-default config workable" for the discovery UI.
        """
        import socket
        from urllib.parse import urlparse
        base_url = getattr(cfg, "TEI_BASE_URL", "http://tei:8080")
        try:
            p = urlparse(base_url)
            with socket.create_connection((p.hostname or "tei", p.port or 8080), timeout=1):
                return True, f"Semantic boundaries · default embed TEI · {base_url}"
        except OSError:
            return False, (
                f"Default TEI at {base_url} unreachable — pick another embed provider "
                f"(openai_compat / openai) under split_method.embed."
            )


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
        from libs.engine.stages.chunking.sentence_window_splitter import SentenceWindowSplitter
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
