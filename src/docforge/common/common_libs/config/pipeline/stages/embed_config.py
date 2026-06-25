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
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.config.pipeline._helpers import _lift_provider_to_chain
from common_libs.config.pipeline.spec_utils import normalize_legacy_id as _normalize_legacy_id


# Legacy embed provider ids that have been collapsed into a current choice. Stored pipelines
# may still carry these; they are rewritten to the canonical id BEFORE the discriminated-union
# dispatch so old configs keep loading. `tei` → `bge_server`: the off-the-shelf TEI image was
# replaced by the local bge_server host, which speaks the same TEI HTTP contract and shares the
# same compatible fields (base_url, api_key, model, batch_size, embed_sparse, locality).
_LEGACY_EMBED_ID_ALIASES: dict[str, str] = {"tei": "bge_server"}


class EmbedConfig(BaseModel):
    """
    S6 embedding + indexing configuration (spec §4.7).

    Two backends are available:

    ``BgeServerEmbedConfig`` (id="bge_server") — local bge_server host (BGE-M3, dense 1024-dim +
        native multilingual sparse). Speaks the TEI HTTP contract. Optional: ``base_url``
        (default ``http://bge_server:80``), ``model`` (default ``BAAI/bge-m3``), ``batch_size``,
        ``embed_sparse``, ``timeout_s``. This is the default when the chain is empty.

    ``OpenAICompatEmbedConfig`` (id="openai_compat") — OpenAI-compatible server, local OR external.
        ``locality`` flag: "local" (vLLM/Ollama, api_key optional) or "external" (cloud, api_key
        required).

    Backward-compat: a stored spec with the legacy ``id="tei"`` is rewritten to ``id="bge_server"``
    before validation (see ``_LEGACY_EMBED_ID_ALIASES``); the compatible fields are carried over and
    bge_server's extra ``timeout_s`` falls back to its own default.

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
    # Embed defaults to failure_policy="raise": there is no index without vectors, so an
    # exhausted embed chain fails the document with a precise reason. An expert may set
    # failure_policy="continue" per-collection (the batch then contributes no vectors).
    gate: ChainGateConfig = Field(
        default_factory=lambda: ChainGateConfig(failure_policy="raise"),
        description="Escalation + exhaustion policy for the embedding chain (default failure_policy=raise).",
    )

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """
        Normalize legacy shapes before the discriminated-union dispatch.

        Steps:
        1. Lift a legacy ``{provider: {...}}`` into ``{chain: [{...}]}``.
        2. Rewrite legacy provider ids (e.g. ``tei`` → ``bge_server``) in every chain entry and
           in the optional separate ``sparse`` backend, so configs stored against a now-removed
           choice still validate against the current union. Uses the shared
           ``normalize_legacy_id`` helper with ``_LEGACY_EMBED_ID_ALIASES``.
        """
        if not isinstance(v, dict):
            return v
        # 1. Lift the legacy single-provider shape into the chain shape.
        v = dict(v)
        v = _lift_provider_to_chain(v, chain_key="chain", provider_key="provider")
        # 2. Rewrite legacy ids in the chain entries and the separate sparse backend.
        chain = v.get("chain")
        if isinstance(chain, list):
            v["chain"] = [_normalize_legacy_id(item, _LEGACY_EMBED_ID_ALIASES) for item in chain]
        if "sparse" in v:
            v["sparse"] = _normalize_legacy_id(v["sparse"], _LEGACY_EMBED_ID_ALIASES)
        return v

    @model_validator(mode="after")
    def _validate_and_default_embed_chain(self) -> EmbedConfig:
        """
        Validate each item in the embed chain via the discriminated union, then default.

        When the chain is empty: default to [BgeServerEmbedConfig()] (bge_server is the default
        embed provider; the legacy ``tei`` choice was removed).
        When items are dicts (round-tripped from DB/JSON): coerce them through the
        TypeAdapter so unknown ids raise ValidationError immediately (not at registry time).
        Legacy ``tei`` specs are already rewritten to ``bge_server`` by ``_compat`` (mode="before").
        """
        # Lazy imports to preserve the leaf constraint.
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from common_libs.providers.embed.bge_server.config import BgeServerEmbedConfig
        from common_libs.providers.embed.openai_compat.config import OpenAICompatEmbedConfig

        if not self.chain:
            object.__setattr__(self, "chain", [BgeServerEmbedConfig()])
            return self

        # Build the discriminated union from the (post-merge) embed configs. `tei` is intentionally
        # absent — it was unregistered and is normalized to `bge_server` upstream in _compat.
        union = Annotated[
            BgeServerEmbedConfig | OpenAICompatEmbedConfig,
            _F(discriminator="id"),
        ]
        adapter = TypeAdapter(union)

        # Coerce/validate each item — raises ValidationError on unknown id.
        object.__setattr__(self, "chain", [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ])

        # Coerce the optional separate sparse backend through the same union.
        if isinstance(self.sparse, dict):
            object.__setattr__(self, "sparse", adapter.validate_python(self.sparse))
        return self
