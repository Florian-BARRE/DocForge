# ====== Code Summary ======
# Request/response models for the collection cost-estimate endpoint, mirrored field-for-field from the
# DocForge backend. The request (CollectionEstimateRequest) picks which documents to project over; the
# response (CostEstimate) is the pure pre-hoc breakdown returned verbatim by the backend — its
# assumptions (EstimateAssumptions), per-stage usage (StageEstimate) and projected material volume
# (VolumeEstimate) are all surfaced so an estimate is never mistaken for an exact quote.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class CollectionEstimateRequest(BaseModel):
    """
    Body of the estimate endpoint — which documents to project the cost over.

    Attributes:
        scope (Literal): Which documents the estimate covers — ``pending`` (uploaded but not yet
            ingested, the default preview target) or ``all`` (every document in the collection).
    """

    scope: Literal["pending", "all"] = Field(
        default="pending",
        description="Documents to estimate over: 'pending' (not-yet-ingested) or 'all'.",
    )


class EstimateAssumptions(BaseModel):
    """
    The tunable assumptions that turn raw document stats into per-stage token/volume figures.

    Surfaced verbatim in the response so an estimate is never mistaken for an exact quote: the reader
    sees exactly which averages produced it. Chunk sizing is read from the collection's chunker
    config; the rest are estimator defaults.

    Attributes:
        tokens_per_page (float): Assumed body-text tokens per page (PDF-derived docs).
        bytes_per_token (float): Assumed bytes per token for text-native formats.
        bytes_per_page (float): Assumed bytes per page for binary documents without a page count.
        target_chunk_tokens (int): Chunk size (from the collection's chunker config).
        chunk_overlap_ratio (float): Fraction of tokens re-embedded as overlap between chunks.
        images_per_page (float): Assumed figures/images per page — the biggest uncertainty.
        scanned_page_ratio (float): Fraction of pages assumed to need paid OCR (escalation-only).
        llm_prompt_overhead_tokens (float): Prompt tokens per LLM call beyond the chunk body.
        llm_output_tokens (float): Completion tokens per contextualize LLM call.
        metagen_doc_context_tokens (float): Prompt tokens fed per document-scope metagen call.
        metagen_output_tokens_per_field (float): Completion tokens per generated metadata field.
        vlm_prompt_tokens_per_image (float): Prompt tokens per VLM call (image tokens + instruction).
        vlm_output_tokens (float): Completion tokens per VLM caption call.
        embed_dense_dims (int): Dense vector dimensionality (for the storage estimate).
    """

    tokens_per_page: float = Field(
        default=500.0, description="Assumed body-text tokens per page (PDF-derived docs)."
    )
    bytes_per_token: float = Field(
        default=4.0, description="Assumed bytes per token for text-native formats."
    )
    bytes_per_page: float = Field(
        default=40000.0,
        description="Assumed bytes per page for binary documents without a known page count.",
    )
    target_chunk_tokens: int = Field(
        default=512, description="Chunk size (from the collection's chunker config)."
    )
    chunk_overlap_ratio: float = Field(
        default=0.0, description="Fraction of tokens re-embedded as overlap between chunks."
    )
    images_per_page: float = Field(
        default=0.5,
        description="Assumed figures/images per page — the biggest uncertainty (unknown until parse).",
    )
    scanned_page_ratio: float = Field(
        default=0.0,
        description="Fraction of pages assumed to need paid OCR (escalation-only; 0 by default).",
    )
    llm_prompt_overhead_tokens: float = Field(
        default=400.0, description="Prompt tokens per LLM call beyond the chunk body."
    )
    llm_output_tokens: float = Field(
        default=250.0, description="Completion tokens per contextualize LLM call."
    )
    metagen_doc_context_tokens: float = Field(
        default=2000.0, description="Prompt tokens fed per document-scope metagen call."
    )
    metagen_output_tokens_per_field: float = Field(
        default=40.0, description="Completion tokens per generated metadata field."
    )
    vlm_prompt_tokens_per_image: float = Field(
        default=1000.0, description="Prompt tokens per VLM call (image tokens + instruction)."
    )
    vlm_output_tokens: float = Field(
        default=300.0, description="Completion tokens per VLM caption call."
    )
    embed_dense_dims: int = Field(
        default=1024, description="Dense vector dimensionality (for the storage estimate)."
    )


class StageEstimate(BaseModel):
    """
    One cost-incurring stage's projected usage and cost.

    Attributes:
        stage (str): Stage key (embed / contextualize / metagen_chunk / …).
        family (str): The capability family that spends (embed / llm / vlm / ocr).
        provider (str): The selected provider kind.
        model (str | None): The priced model id (None for OCR/local).
        calls (int): Projected number of provider calls.
        prompt_tokens (int): Projected input/prompt tokens.
        completion_tokens (int): Projected output/completion tokens.
        pages (int): Projected pages billed (OCR only).
        cost_usd (float | None): Projected USD cost — 0.0 for a known-local provider, None when the
            model has no known rate (usage is still reported).
        rate_known (bool): Whether a rate was found; False ⇒ cost is null (unknown), not zero.
    """

    stage: str = Field(description="Stage key (embed / contextualize / metagen_chunk / …).")
    family: str = Field(description="The capability family that spends (embed / llm / vlm / ocr).")
    provider: str = Field(description="The selected provider kind.")
    model: str | None = Field(default=None, description="The priced model id (None for OCR/local).")
    calls: int = Field(description="Projected number of provider calls.")
    prompt_tokens: int = Field(description="Projected input/prompt tokens.")
    completion_tokens: int = Field(description="Projected output/completion tokens.")
    pages: int = Field(default=0, description="Projected pages billed (OCR only).")
    cost_usd: float | None = Field(
        description="Projected USD cost — 0.0 for a known-local provider, None when the model has "
        "no known rate (usage is still reported)."
    )
    rate_known: bool = Field(
        description="Whether a rate was found; False ⇒ cost is null (unknown), not zero."
    )


class VolumeEstimate(BaseModel):
    """
    The projected material volume of the ingestion.

    Attributes:
        pages (int): Total pages across the covered documents.
        chunks (int): Projected chunk count.
        dense_vectors (int): Projected dense vectors written (0 if no embed).
        sparse_vectors (int): Projected sparse vectors written.
        storage_bytes (int): Rough total storage footprint (text + vectors).
    """

    pages: int = Field(description="Total pages across the covered documents.")
    chunks: int = Field(description="Projected chunk count.")
    dense_vectors: int = Field(description="Projected dense vectors written (0 if no embed).")
    sparse_vectors: int = Field(description="Projected sparse vectors written.")
    storage_bytes: int = Field(description="Rough total storage footprint (text + vectors).")


class CostEstimate(BaseModel):
    """
    The full pre-hoc breakdown — an ESTIMATE, with its assumptions and caveats surfaced.

    ``total_cost_usd`` sums only the stages with a known rate; ``cost_complete`` is False when any
    enabled cost-incurring stage priced to null, so the total is understood as a lower bound.

    Attributes:
        document_count (int): Documents the estimate covers.
        stages (list[StageEstimate]): Per-stage projected usage and cost (enabled stages only).
        volume (VolumeEstimate): Projected material volume.
        total_prompt_tokens (int): Summed projected prompt/input tokens.
        total_completion_tokens (int): Summed projected completion tokens.
        total_cost_usd (float | None): Summed USD over priced stages (None only when NO stage could
            be priced).
        cost_complete (bool): True when every enabled cost-incurring stage had a known rate.
        assumptions (EstimateAssumptions): The assumptions this estimate rests on.
        caveats (list[str]): Human-readable accuracy caveats for this estimate.
    """

    document_count: int = Field(description="Documents the estimate covers.")
    stages: list[StageEstimate] = Field(
        default_factory=list,
        description="Per-stage projected usage and cost (enabled stages only).",
    )
    volume: VolumeEstimate = Field(description="Projected material volume.")
    total_prompt_tokens: int = Field(description="Summed projected prompt/input tokens.")
    total_completion_tokens: int = Field(description="Summed projected completion tokens.")
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
    "CollectionEstimateRequest",
    "EstimateAssumptions",
    "StageEstimate",
    "VolumeEstimate",
    "CostEstimate",
]
