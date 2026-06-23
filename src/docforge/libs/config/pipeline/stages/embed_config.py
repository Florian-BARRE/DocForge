# ====== Code Summary ======
# S6 EmbedConfig: embedding and indexing configuration for the DocForge pipeline.
# Wraps the ordered embedding-backend chain (TEI / LocalOpenAI / OpenAI) with a
# gated escalation policy.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config — all concrete-provider imports stay LAZY
# (inside model_validator bodies).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.config.pipeline.chain_gate_config import ChainGateConfig
from libs.config.pipeline._helpers import _lift_provider_to_chain


class EmbedConfig(BaseModel):
    """
    S6 embedding + indexing configuration (spec §4.7).

    Three backends are available:

    ``TeiEmbedConfig`` (id="tei") — local TEI server (BGE-M3, dense 1024-dim + sparse BM25).
        Required params: ``base_url`` (e.g. ``http://tei:8080``).
        Optional: ``model`` (default ``BAAI/bge-m3``), ``batch_size``, ``embed_sparse``.

    ``LocalOpenAIEmbedConfig`` (id="openai_compat") — self-hosted OpenAI-compatible server.
        Required params: ``base_url``.  Optional: ``api_key``, ``model``, ``batch_size``.

    ``OpenAIEmbedConfig`` (id="openai") — external cloud API (OpenAI, Azure, Mistral, Cohere).
        Required params: ``base_url``, ``api_key`` (mandatory — raises if empty).

    Attributes:
        chain (list[EmbedProviderConfig]): Ordered DENSE embedding backends; index 0 is tried first.
        sparse (EmbedProviderConfig | None): Optional SEPARATE sparse backend. When set, sparse
            (BM25/lexical) vectors are sourced from it instead of the dense chain — required to
            get hybrid search with a dense-only chain (e.g. OpenAI, or TEI/BGE-M3 cls pooling).
            None means sparse comes from the chain provider itself (e.g. a SPLADE TEI).
        gate (ChainGateConfig): Escalation policy for the embedding chain.
    """

    chain: list[Any] = Field(
        default_factory=list,
        description="Ordered dense embedding backends; index 0 is tried first.",
    )
    sparse: Any = Field(
        default=None,
        description="Optional separate sparse backend; None = sparse comes from the chain provider.",
    )
    gate: ChainGateConfig = Field(
        default_factory=ChainGateConfig,
        description="Escalation policy for the embedding chain.",
    )

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Lift legacy ``{provider: {...}}`` to ``{chain: [{...}]}`` and flatten entries."""
        if not isinstance(v, dict):
            return v
        v = dict(v)
        v = _lift_provider_to_chain(v, chain_key="chain", provider_key="provider")
        return v

    @model_validator(mode="after")
    def _validate_and_default_embed_chain(self) -> EmbedConfig:
        """
        Validate each item in the embed chain via the discriminated union, then default.

        When the chain is empty: default to [TeiEmbedConfig()].
        When items are dicts (round-tripped from DB/JSON): coerce them through the
        TypeAdapter so unknown ids raise ValidationError immediately (not at registry time).
        """
        # Lazy imports to preserve the leaf constraint.
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from libs.providers.embed.external.openai_compat_config import OpenAIEmbedConfig
        from libs.providers.embed.local.config import TeiEmbedConfig
        from libs.providers.embed.local.openai_compat_config import LocalOpenAIEmbedConfig

        if not self.chain:
            object.__setattr__(self, "chain", [TeiEmbedConfig()])
            return self

        # Build the discriminated union from all known embed configs.
        union = Annotated[
            TeiEmbedConfig | LocalOpenAIEmbedConfig | OpenAIEmbedConfig,
            _F(discriminator="id"),
        ]
        adapter = TypeAdapter(union)

        # Coerce/validate each item — raises ValidationError on unknown id.
        coerced = [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ]
        object.__setattr__(self, "chain", coerced)

        # Coerce the optional separate sparse backend through the same union.
        if isinstance(self.sparse, dict):
            object.__setattr__(self, "sparse", adapter.validate_python(self.sparse))
        return self
