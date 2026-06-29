# ====== Code Summary ======
# IngestStageEmbedIndexConfig — the pure-setting knob of the embed_index stage, co-located with the
# node and declared as its ``Config``. The embed provider chain and the collection metadata fields are
# assembly/run concerns (injected as services), so the only construction-time knob here is the embed
# batch size: how many texts are sent per embed-chain attempt. The field carries a ``description`` so
# the discovery API renders a labelled form with zero hardcoded text. Frozen + strict (inherited from
# StageConfigBase): an out-of-contract value fails fast at assembly.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from common_libs.pipelines import StageConfigBase


class IngestStageEmbedIndexConfig(StageConfigBase):
    """
    Embed & index stage configuration — the embedding batch size.

    The embed provider chain (which dense/sparse backends, their order, the escalation gate) and the
    collection's metadata fields are NOT knobs here: they are resolved by the assembler and injected as
    services. The only pure setting is how many texts are batched per embed-chain attempt, shared by
    both the chunk-body embed step and the metadata-field embed step.

    Attributes:
        embed_batch_size (int): Texts sent per embed-chain attempt (>= 1).
    """

    embed_batch_size: int = Field(
        default=64,
        ge=1,
        description=(
            "Number of texts sent to the embedding backend per request, shared by the chunk-body and "
            "metadata-field embed steps. Higher values improve throughput but raise per-request memory "
            "and latency; lower values are gentler on the backend. Must be at least 1."
        ),
    )


__all__ = ["IngestStageEmbedIndexConfig"]
