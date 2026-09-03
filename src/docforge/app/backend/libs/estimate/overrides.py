# ====== Code Summary ======
# The per-collection cost-estimate override contract — the typed, PARTIAL overlay a collection may
# carry over the global estimator defaults (the canonical RateTable + EstimateAssumptions). Every
# field is optional and every model is ``extra="forbid"``: an absent subtree falls through to the
# default, and a typo in a rate/assumption key fails validation loudly instead of being silently
# dropped (which would produce a wrong estimate). This is both the stored shape (collection.
# estimate_overrides JSONB) and the read/write API shape — the merger (merger.py) folds it over the
# defaults; no arithmetic lives here.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class ModelRateOverride(BaseModel):
    """One chat/LLM/VLM model's (input, output) price override, USD per 1M tokens."""

    model_config = ConfigDict(extra="forbid")

    input: float = Field(ge=0.0, description="Input/prompt price, USD per 1M tokens.")
    output: float = Field(ge=0.0, description="Output/completion price, USD per 1M tokens.")


class RateOverrides(BaseModel):
    """Partial overrides of the three rate maps the estimator prices against (absent map = default)."""

    model_config = ConfigDict(extra="forbid")

    models: dict[str, ModelRateOverride] | None = Field(
        default=None,
        description="Chat model id → (input, output) USD/1M-token override (merged over defaults).",
    )
    embed: dict[str, float] | None = Field(
        default=None,
        description="Embedding model id → USD/1M-token override (merged over defaults).",
    )
    ocr: dict[str, float] | None = Field(
        default=None,
        description="OCR provider kind → USD/page override (merged over defaults).",
    )


class AssumptionOverrides(BaseModel):
    """
    Partial overrides of the estimator's extrapolation assumptions (absent field = default).

    Mirrors ``EstimateAssumptions`` field-for-field, but every field is optional so a caller overrides
    only what it means to. ``target_chunk_tokens`` / ``chunk_overlap_ratio`` may be set here, but the
    collection's ACTUAL chunker config still wins on top (the pipeline is authoritative for chunk
    sizing) — see the merger.
    """

    model_config = ConfigDict(extra="forbid")

    tokens_per_page: float | None = Field(
        default=None, gt=0.0, description="Body-text tokens/page."
    )
    bytes_per_token: float | None = Field(
        default=None, gt=0.0, description="Bytes/token for text-native formats."
    )
    bytes_per_page: float | None = Field(
        default=None, gt=0.0, description="Bytes/page for binary docs without a known page count."
    )
    target_chunk_tokens: int | None = Field(
        default=None, gt=0, description="Chunk size (the pipeline's chunker config wins on top)."
    )
    chunk_overlap_ratio: float | None = Field(
        default=None, ge=0.0, description="Overlap fraction (the chunker config wins on top)."
    )
    images_per_page: float | None = Field(
        default=None, ge=0.0, description="Assumed figures/images per page (drives enrich volume)."
    )
    scanned_page_ratio: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Fraction of pages assumed to need paid OCR."
    )
    llm_prompt_overhead_tokens: float | None = Field(
        default=None, ge=0.0, description="Prompt tokens per LLM call beyond the chunk body."
    )
    llm_output_tokens: float | None = Field(
        default=None, ge=0.0, description="Completion tokens per contextualize LLM call."
    )
    metagen_doc_context_tokens: float | None = Field(
        default=None, ge=0.0, description="Prompt tokens fed per document-scope metagen call."
    )
    metagen_output_tokens_per_field: float | None = Field(
        default=None, ge=0.0, description="Completion tokens per generated metadata field."
    )
    vlm_prompt_tokens_per_image: float | None = Field(
        default=None, ge=0.0, description="Prompt tokens per VLM call (image + instruction)."
    )
    vlm_output_tokens: float | None = Field(
        default=None, ge=0.0, description="Completion tokens per VLM caption call."
    )
    embed_dense_dims: int | None = Field(
        default=None, gt=0, description="Dense vector dimensionality (for the storage estimate)."
    )


class EstimateOverrides(BaseModel):
    """
    A collection's PARTIAL override of the cost-estimate inputs — rates and/or assumptions.

    Stored verbatim (as a partial dict) in ``collection.estimate_overrides`` and echoed on the
    collection read. NULL / an absent subtree means "use the global default"; a provided value is
    deep-merged over the default by the merger. No provider secrets are involved (rates only), so it
    is neither masked nor restored on the round-trip.
    """

    model_config = ConfigDict(extra="forbid")

    rates: RateOverrides | None = Field(
        default=None, description="Partial rate-map overrides (chat / embed / OCR)."
    )
    assumptions: AssumptionOverrides | None = Field(
        default=None, description="Partial extrapolation-assumption overrides."
    )


__all__ = [
    "ModelRateOverride",
    "RateOverrides",
    "AssumptionOverrides",
    "EstimateOverrides",
]
