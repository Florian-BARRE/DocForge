# ====== Code Summary ======
# The config of the ``(embed, dense_sparse)`` node — TWO independent provider slots plus the shared
# batching / per-field switches. Each slot is ``{kind, …that kind's config…}`` or null (axis off):
#   - dense  → bge_server | openai_compatible (any provider serving the dense axis);
#   - sparse → bge_server | bm25_local       (any provider serving the sparse axis).
# A slot is validated against its kind's own config class through EmbedProviderRegistry (extra=
# "forbid" applies inside the slot), so a new provider kind needs no edit here. At least one slot
# must be set. The omitted-slot default is the in-stack bge_server — the same server on both axes,
# which the node turns into ONE combined /embed_all call per batch.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field, SerializeAsAny, field_validator, model_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig

# ====== Local Project Imports ======
from ..providers import (
    BgeServerProviderConfig,
    EmbedAxis,
    EmbedProviderConfig,
    EmbedProviderRegistry,
)

# The in-stack model host the stock pipeline embeds through (compose service name).
IN_STACK_BGE_URL = "http://bge_server:80"


def _in_stack_bge() -> BgeServerProviderConfig:
    """The stock slot provider: the in-stack bge_server."""
    return BgeServerProviderConfig(base_url=IN_STACK_BGE_URL)


class EmbedDenseSparseConfig(NodeConfig):
    """Independent dense and sparse provider slots (null = that axis off) + shared knobs."""

    dense: SerializeAsAny[EmbedProviderConfig] | None = Field(
        default_factory=_in_stack_bge,
        description="The DENSE provider slot — {kind, …its config} (kinds: bge_server, "
        "openai_compatible), or null for a sparse-only collection (no semantic search).",
    )
    sparse: SerializeAsAny[EmbedProviderConfig] | None = Field(
        default_factory=_in_stack_bge,
        description="The SPARSE provider slot — {kind, …its config} (kinds: bge_server = learned "
        "sparse weights, bm25_local = in-process BM25 scored with the store's IDF), or null for a "
        "dense-only collection (no lexical search). Encodes the content AND the metadata lexical "
        "vectors, at index and at query time. Same bge_server endpoint as the dense slot → one "
        "combined call, made with the DENSE slot's api_key and retry/timeout/concurrency policy "
        "(this slot's own are then unused).",
    )
    batch_size: int = Field(default=32, gt=0, description="Texts embedded per provider call.")
    embed_semantic_fields: bool = Field(
        default=False,
        description="Also embed each SEMANTIC chunk-scope contract field's value as a named per-field "
        "dense vector (meta_<slug>_dense) — needs a dense slot. OFF by default (extra cost).",
    )
    embed_lexical_fields: bool = Field(
        default=False,
        description="Also encode each LEXICAL chunk-scope contract field's value as a named per-field "
        "sparse vector (meta_<slug>_bm25) — needs a sparse slot. OFF by default (extra cost).",
    )

    @field_validator("dense", mode="before")
    @classmethod
    def _validate_dense(cls, value: Any) -> Any:
        """Dispatch the dense slot to its kind's config class (null keeps the axis off)."""
        return None if value is None else EmbedProviderRegistry.validate(EmbedAxis.DENSE, value)

    @field_validator("sparse", mode="before")
    @classmethod
    def _validate_sparse(cls, value: Any) -> Any:
        """Dispatch the sparse slot to its kind's config class (null keeps the axis off)."""
        return None if value is None else EmbedProviderRegistry.validate(EmbedAxis.SPARSE, value)

    @model_validator(mode="after")
    def _one_slot_at_least(self) -> "EmbedDenseSparseConfig":
        """An embedder with neither axis indexes nothing — disable the embed stage instead."""
        if self.dense is None and self.sparse is None:
            raise ValueError("set a dense and/or a sparse provider (both slots are null)")
        return self


__all__ = ["EmbedDenseSparseConfig", "IN_STACK_BGE_URL"]
