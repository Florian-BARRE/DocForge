# ====== Code Summary ======
# Request/response models for the collection cost-estimate endpoint, mirrored field-for-field from the
# DocForge backend. The request (CollectionEstimateRequest) picks which documents to project over —
# either a whole-collection scope, an explicit document-id subset, or a corpus filter subset (the SAME
# shape the document grid uses); the response (CostEstimate) is the pure pre-hoc breakdown returned
# verbatim by the backend — its assumptions (EstimateAssumptions), per-stage usage (StageEstimate) and
# projected material volume (VolumeEstimate) are all surfaced so an estimate is never mistaken for an
# exact quote. EstimateOverrides (+ its RateOverrides/ModelRateOverride/AssumptionOverrides parts)
# mirror app/backend/libs/estimate/overrides.py — the PARTIAL, per-collection overlay a collection may
# carry over the global estimator defaults; it round-trips on CollectionModel.estimate_overrides and
# UpdateCollectionRequest.estimate_overrides.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Local Project Imports ======
from .corpus import DocumentFilter


class CollectionEstimateRequest(BaseModel):
    """
    Body of the estimate endpoint — which documents to project the cost over.

    Three mutually-refining selectors, in precedence order: an explicit ``document_ids`` subset, a
    corpus ``filter`` subset (the SAME shape the document grid uses), or — when neither is given —
    the whole-collection ``scope``. ``document_ids`` and ``filter`` are mutually exclusive.

    Attributes:
        scope (Literal): Whole-collection selector when no subset is given — ``pending`` (uploaded
            but not yet ingested, the default preview target) or ``all`` (every document).
        document_ids (list[str] | None): Estimate over exactly these documents (must exist and belong
            to the collection). Mutually exclusive with ``filter``.
        filter (DocumentFilter | None): Estimate over the documents matching this corpus filter (the
            document-grid filter shape). Mutually exclusive with ``document_ids``.
    """

    scope: Literal["pending", "all"] = Field(
        default="pending",
        description="Whole-collection selector when no subset is given: 'pending' or 'all'.",
    )
    document_ids: list[str] | None = Field(
        default=None,
        description="Estimate over exactly these document ids (mutually exclusive with 'filter').",
    )
    filter: DocumentFilter | None = Field(
        default=None,
        description="Estimate over the documents matching this corpus filter (mutually exclusive "
        "with 'document_ids').",
    )

    @model_validator(mode="after")
    def _validate_selection(self) -> "CollectionEstimateRequest":
        """Enforce the document_ids-XOR-filter contract and a non-empty explicit id list."""
        # 1. Never both subset selectors at once — the target set would be ambiguous.
        if self.document_ids is not None and self.filter is not None:
            raise ValueError("Provide at most one of 'document_ids' or 'filter'.")
        # 2. An explicit id list, when present, must select something.
        if self.document_ids is not None and not self.document_ids:
            raise ValueError("'document_ids' must be a non-empty list when provided.")
        return self


class ModelRateOverride(BaseModel):
    """
    One chat/LLM/VLM model's (input, output) price override, USD per 1M tokens.

    Attributes:
        input (float): Input/prompt price, USD per 1M tokens.
        output (float): Output/completion price, USD per 1M tokens.
    """

    input: float = Field(ge=0.0, description="Input/prompt price, USD per 1M tokens.")
    output: float = Field(ge=0.0, description="Output/completion price, USD per 1M tokens.")


class RateOverrides(BaseModel):
    """
    Partial overrides of the three rate maps the estimator prices against (absent map = default).

    Attributes:
        models (dict[str, ModelRateOverride] | None): Chat model id → (input, output) USD/1M-token
            override (merged over defaults).
        embed (dict[str, float] | None): Embedding model id → USD/1M-token override.
        ocr (dict[str, float] | None): OCR provider kind → USD/page override.
    """

    models: dict[str, ModelRateOverride] | None = Field(
        default=None,
        description="Chat model id -> (input, output) USD/1M-token override (merged over defaults).",
    )
    embed: dict[str, float] | None = Field(
        default=None,
        description="Embedding model id -> USD/1M-token override (merged over defaults).",
    )
    ocr: dict[str, float] | None = Field(
        default=None,
        description="OCR provider kind -> USD/page override (merged over defaults).",
    )


class AssumptionOverrides(BaseModel):
    """
    Partial overrides of the estimator's extrapolation assumptions (absent field = default).

    Mirrors ``EstimateAssumptions`` field-for-field, but every field is optional so a caller overrides
    only what it means to. ``target_chunk_tokens`` / ``chunk_overlap_ratio`` may be set here, but the
    collection's ACTUAL chunker config still wins on top (the pipeline is authoritative for chunk
    sizing).

    Attributes:
        tokens_per_page (float | None): Body-text tokens/page.
        bytes_per_token (float | None): Bytes/token for text-native formats.
        bytes_per_page (float | None): Bytes/page for binary docs without a known page count.
        target_chunk_tokens (int | None): Chunk size (the pipeline's chunker config wins on top).
        chunk_overlap_ratio (float | None): Overlap fraction (the chunker config wins on top).
        images_per_page (float | None): Assumed figures/images per page (drives enrich volume).
        scanned_page_ratio (float | None): Fraction of pages assumed to need paid OCR.
        llm_prompt_overhead_tokens (float | None): Prompt tokens per LLM call beyond the chunk body.
        llm_output_tokens (float | None): Completion tokens per contextualize LLM call.
        metagen_doc_context_tokens (float | None): Prompt tokens fed per document-scope metagen call.
        metagen_output_tokens_per_field (float | None): Completion tokens per generated field.
        vlm_prompt_tokens_per_image (float | None): Prompt tokens per VLM call (image + instruction).
        vlm_output_tokens (float | None): Completion tokens per VLM caption call.
        embed_dense_dims (int | None): Dense vector dimensionality (for the storage estimate).
    """

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
    deep-merged over the default by the backend. No provider secrets are involved (rates only), so it
    is neither masked nor restored on the round-trip.

    Attributes:
        rates (RateOverrides | None): Partial rate-map overrides (chat / embed / OCR).
        assumptions (AssumptionOverrides | None): Partial extrapolation-assumption overrides.
    """

    rates: RateOverrides | None = Field(
        default=None, description="Partial rate-map overrides (chat / embed / OCR)."
    )
    assumptions: AssumptionOverrides | None = Field(
        default=None, description="Partial extrapolation-assumption overrides."
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
    "ModelRateOverride",
    "RateOverrides",
    "AssumptionOverrides",
    "EstimateOverrides",
    "EstimateAssumptions",
    "StageEstimate",
    "VolumeEstimate",
    "CostEstimate",
]
