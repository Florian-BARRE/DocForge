# ====== Code Summary ======
# The pure data contracts of the pre-hoc ingestion cost/volume estimator: the sampled document
# statistics fed in (SampleStats), the surfaced assumptions that drive the extrapolation
# (EstimateAssumptions), and the structured breakdown returned (StageEstimate, VolumeEstimate,
# CostEstimate). Every model is plain Pydantic with described fields — no DB, no network, no config
# — so the estimator core stays pure and directly serialisable as an API response.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class SampleStats(BaseModel):
    """
    Aggregated statistics of the documents an estimate is projected over.

    These are gathered at the edge (DB rows, optional cheap probe) and handed to the pure estimator.
    ``sampled_documents`` may be smaller than ``document_count`` when only a sample was measured; the
    estimator scales linearly by ``document_count / sampled_documents``.
    """

    model_config = ConfigDict(extra="forbid")

    document_count: int = Field(ge=0, description="Total documents the estimate covers.")
    sampled_documents: int = Field(
        ge=0, description="Documents actually measured (< document_count ⇒ the rest is scaled)."
    )
    total_pages: float = Field(ge=0.0, description="Summed page count over the sampled documents.")
    total_text_tokens: float = Field(
        ge=0.0, description="Summed estimated body-text tokens over the sampled documents."
    )
    pages_from_probe: int = Field(
        default=0,
        ge=0,
        description="How many sampled documents contributed an EXACT page count (vs a size-derived "
        "estimate) — surfaced so the caller can judge accuracy.",
    )


class EstimateAssumptions(BaseModel):
    """
    The tunable assumptions that turn raw document stats into per-stage token/volume figures.

    Surfaced verbatim in the response so an estimate is never mistaken for an exact quote: the reader
    sees exactly which averages produced it. Chunk sizing is read from the collection's chunker
    config; the rest are estimator defaults.
    """

    model_config = ConfigDict(extra="forbid")

    tokens_per_page: float = Field(
        default=500.0, gt=0.0, description="Assumed body-text tokens per page (PDF-derived docs)."
    )
    bytes_per_token: float = Field(
        default=4.0, gt=0.0, description="Assumed bytes per token for text-native formats."
    )
    bytes_per_page: float = Field(
        default=40000.0,
        gt=0.0,
        description="Assumed bytes per page for binary documents without a known page count "
        "(edge-sampling assumption; the true count is set at ingest by pdf_probe).",
    )
    target_chunk_tokens: int = Field(
        default=512, gt=0, description="Chunk size (from the collection's chunker config)."
    )
    chunk_overlap_ratio: float = Field(
        default=0.0, ge=0.0, description="Fraction of tokens re-embedded as overlap between chunks."
    )
    images_per_page: float = Field(
        default=0.5,
        ge=0.0,
        description="Assumed figures/images per page — the biggest uncertainty (true figure count "
        "is unknown until parse). Drives the enrich VLM/OCR volume.",
    )
    scanned_page_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of pages assumed to need paid OCR (escalation-only; 0 by default).",
    )
    llm_prompt_overhead_tokens: float = Field(
        default=400.0, ge=0.0, description="Prompt tokens per LLM call beyond the chunk body."
    )
    llm_output_tokens: float = Field(
        default=250.0, ge=0.0, description="Completion tokens per contextualize LLM call."
    )
    metagen_doc_context_tokens: float = Field(
        default=2000.0, ge=0.0, description="Prompt tokens fed per document-scope metagen call."
    )
    metagen_output_tokens_per_field: float = Field(
        default=40.0, ge=0.0, description="Completion tokens per generated metadata field."
    )
    vlm_prompt_tokens_per_image: float = Field(
        default=1000.0,
        ge=0.0,
        description="Prompt tokens per VLM call (image tokens + instruction).",
    )
    vlm_output_tokens: float = Field(
        default=300.0, ge=0.0, description="Completion tokens per VLM caption call."
    )
    embed_dense_dims: int = Field(
        default=1024, gt=0, description="Dense vector dimensionality (for the storage estimate)."
    )


class StageEstimate(BaseModel):
    """One cost-incurring stage's projected usage and cost."""

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(description="Stage key (embed / contextualize / metagen_chunk / …).")
    family: str = Field(description="The capability family that spends (embed / llm / vlm / ocr).")
    provider: str = Field(description="The selected provider kind.")
    model: str | None = Field(default=None, description="The priced model id (None for OCR/local).")
    calls: int = Field(ge=0, description="Projected number of provider calls.")
    prompt_tokens: int = Field(ge=0, description="Projected input/prompt tokens.")
    completion_tokens: int = Field(ge=0, description="Projected output/completion tokens.")
    pages: int = Field(default=0, ge=0, description="Projected pages billed (OCR only).")
    cost_usd: float | None = Field(
        description="Projected USD cost — 0.0 for a known-local provider, None when the model has "
        "no known rate (usage is still reported)."
    )
    rate_known: bool = Field(
        description="Whether a rate was found; False ⇒ cost is null (unknown), not zero."
    )


class VolumeEstimate(BaseModel):
    """The projected material volume of the ingestion."""

    model_config = ConfigDict(extra="forbid")

    pages: int = Field(ge=0, description="Total pages across the covered documents.")
    chunks: int = Field(ge=0, description="Projected chunk count.")
    dense_vectors: int = Field(ge=0, description="Projected dense vectors written (0 if no embed).")
    sparse_vectors: int = Field(ge=0, description="Projected sparse vectors written.")
    storage_bytes: int = Field(ge=0, description="Rough total storage footprint (text + vectors).")


class CostEstimate(BaseModel):
    """
    The full pre-hoc breakdown — an ESTIMATE, with its assumptions and caveats surfaced.

    ``total_cost_usd`` sums only the stages with a known rate; ``cost_complete`` is False when any
    enabled cost-incurring stage priced to null, so the total is understood as a lower bound.
    """

    model_config = ConfigDict(extra="forbid")

    document_count: int = Field(ge=0, description="Documents the estimate covers.")
    stages: list[StageEstimate] = Field(
        default_factory=list,
        description="Per-stage projected usage and cost (enabled stages only).",
    )
    volume: VolumeEstimate = Field(description="Projected material volume.")
    total_prompt_tokens: int = Field(ge=0, description="Summed projected prompt/input tokens.")
    total_completion_tokens: int = Field(ge=0, description="Summed projected completion tokens.")
    total_cost_usd: float | None = Field(
        description="Summed USD over priced stages (None only when NO stage could be priced)."
    )
    cost_complete: bool = Field(
        description="True when every enabled cost-incurring stage had a known rate."
    )
    assumptions: EstimateAssumptions = Field(description="The assumptions this estimate rests on.")
    caveats: list[str] = Field(
        default_factory=list, description="Human-readable accuracy caveats for this estimate."
    )


__all__ = [
    "SampleStats",
    "EstimateAssumptions",
    "StageEstimate",
    "VolumeEstimate",
    "CostEstimate",
]
