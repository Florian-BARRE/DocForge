# ====== Code Summary ======
# SemanticConfig — typed config + build() for the semantic (embedding-based) intra-section
# split method.  Registered into the "split_method" discriminated union via @register.
# Carries a fully typed embed provider sub-config (TEI / openai_compat / openai), shared with
# S6; backward-compat lifts a legacy flat {base_url: ...} to {embed: {id: tei, base_url}}.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import TYPE_CHECKING, Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.config.pipeline._registry import register
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

if TYPE_CHECKING:
    from libs.pipeline.stages.s4_chunk.strategies.semantic import SemanticSplitter


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
    def _validate_embed(self) -> SemanticConfig:
        """Coerce ``embed`` into a typed EmbedProviderConfig instance after construction."""
        # Lazy import — avoids a circular import at module load time.
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from libs.providers.embed import EmbedProviderConfig  # noqa: F401  (typing alias)
        from libs.providers.embed.external.openai_compat_config import OpenAIEmbedConfig
        from libs.providers.embed.local.config import TeiEmbedConfig
        from libs.providers.embed.local.openai_compat_config import LocalOpenAIEmbedConfig

        # Default to TEI when the field is None (e.g. legacy DB row without embed key).
        if self.embed is None:
            object.__setattr__(self, "embed", TeiEmbedConfig())
            return self

        # Already a typed instance — nothing to do.
        if isinstance(self.embed, (TeiEmbedConfig, LocalOpenAIEmbedConfig, OpenAIEmbedConfig)):
            return self

        # Dict → validate via the same discriminated union the rest of the codebase uses.
        Union_ = Annotated[
            TeiEmbedConfig | LocalOpenAIEmbedConfig | OpenAIEmbedConfig,
            _F(discriminator="id"),
        ]
        adapter = TypeAdapter(Union_)
        object.__setattr__(self, "embed", adapter.validate_python(self.embed))
        return self

    def build(self) -> SemanticSplitter:
        """Instantiate SemanticSplitter with the configured embed provider."""
        from libs.pipeline.stages.s4_chunk.strategies.semantic import SemanticSplitter
        embed_provider = self.embed.build()
        return SemanticSplitter(
            embed_provider=embed_provider,
            max_tokens=self.max_tokens,
            min_tokens=self.min_tokens,
            breakpoint_percentile=self.breakpoint_percentile,
        )

    def merge_defaults(self, cfg: Any) -> SemanticConfig:
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


# ------------------- Public API ------------------- #
__all__ = ["SemanticConfig"]
