# ====== Code Summary ======
# SearchConfig: configuration for the search pipeline stages (query transform + rerank).
# Lives inside PipelineConfig.search — serialized in the collection's pipeline JSONB column.
# No new DB column needed; defaults produce identical behavior to the pre-P7 search path.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.pipeline /
# libs.search — all concrete-provider imports stay LAZY (inside model_validator bodies).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator


class QueryTransformConfig(BaseModel):
    """
    Configuration for query transformation strategies.

    Controls how a user query is rewritten or expanded before retrieval.
    When strategy is "none" (the default), the query is passed through unchanged.

    Attributes:
        strategy: Transform strategy — "none" (passthrough), "rewrite" (LLM cleanup),
            "hyde" (hypothetical document generation), or "multi_query" (N reformulations).
        n_variants: Number of reformulated queries for the "multi_query" strategy.
        llm: LLM provider config (discriminated union); None disables all transforms.
    """

    strategy: Literal["none", "rewrite", "hyde", "multi_query"] = Field(
        default="none",
        description="Query transform strategy — 'none' passes the query through unchanged.",
    )
    n_variants: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of query reformulations for the multi_query strategy.",
    )
    llm: Any = Field(
        default=None,
        description="LLM provider config (discriminated union); None disables all transforms.",
    )

    @model_validator(mode="after")
    def _validate_and_default_llm(self) -> QueryTransformConfig:
        """
        Coerce the llm field through the discriminated union if it is a raw dict.

        When llm is a dict (round-tripped from DB/JSON): coerce through TypeAdapter
        so an unknown id raises ValidationError immediately.
        When strategy is "none", llm is forced to None (no LLM needed).
        """
        # Short-circuit: no LLM needed for passthrough strategy
        if self.strategy == "none":
            object.__setattr__(self, "llm", None)
            return self

        # Skip coercion when already a model instance or None
        if self.llm is None or not isinstance(self.llm, dict):
            return self

        # Lazy import to preserve the leaf constraint. There is a single llm provider id
        # ("openai_compat"); its locality flag ("local" / "external") selects the deployment.
        from pydantic import TypeAdapter

        from libs.providers.llm.openai_compat.config import OpenAICompatLLMConfig

        adapter = TypeAdapter(OpenAICompatLLMConfig)
        object.__setattr__(self, "llm", adapter.validate_python(self.llm))
        return self


class RerankConfig(BaseModel):
    """
    Configuration for the reranking stage.

    When enabled=False (the default), the rerank stage is skipped and retrieval
    results are returned as-is.  When enabled, candidate_k results are fetched
    from Qdrant and then trimmed to top_n by the cross-encoder.

    Attributes:
        enabled: Whether to run the rerank stage.
        candidate_k: Number of candidates to retrieve before reranking.
        top_n: Final number of results to return after reranking.
        chain: Ordered list of rerank provider configs (first entry is used).
    """

    enabled: bool = Field(default=False, description="Enable the rerank stage.")
    candidate_k: int = Field(
        default=50,
        ge=1,
        description="Candidates fetched from Qdrant before reranking.",
    )
    top_n: int = Field(
        default=10,
        ge=1,
        description="Final number of results after reranking.",
    )
    chain: list[Any] = Field(
        default_factory=list,
        description="Ordered rerank provider configs; index 0 is used.",
    )

    @model_validator(mode="after")
    def _validate_and_default_rerank_chain(self) -> RerankConfig:
        """
        Coerce each chain item through the discriminated union if it is a raw dict.

        When enabled=False the chain is not validated (no provider needed).
        """
        # Skip validation when reranking is disabled or chain is empty
        if not self.enabled or not self.chain:
            return self

        # Skip coercion when items are already model instances
        if all(not isinstance(item, dict) for item in self.chain):
            return self

        # Lazy imports to preserve the leaf constraint
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from libs.providers.rerank.cohere.config import CohereRerankConfig
        from libs.providers.rerank.bge.config import BgeRerankerConfig

        union = Annotated[BgeRerankerConfig | CohereRerankConfig, _F(discriminator="id")]
        adapter = TypeAdapter(union)

        coerced = [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ]
        object.__setattr__(self, "chain", coerced)
        return self


class GroupingConfig(BaseModel):
    """
    Configuration for document-level result grouping (Qdrant query_points_groups).

    When enabled, results are grouped by a payload field (default ``document_id``)
    so the response carries the top documents each with their best chunks, rather
    than a flat chunk list.  When disabled (the default), chunk-level results are
    returned unchanged — identical to the pre-grouping behavior.

    Attributes:
        enabled: Whether to group results by ``group_by``.
        group_by: Payload field to group on (must be a filterable/indexed field).
        group_size: Maximum chunks kept per group.
    """

    enabled: bool = Field(default=False, description="Group results by document (or another field).")
    group_by: str = Field(
        default="document_id",
        description="Payload field to group on (must be filterable / indexed).",
    )
    group_size: int = Field(
        default=3, ge=1, le=20, description="Maximum chunks returned per group."
    )


class MmrConfig(BaseModel):
    """
    Configuration for Maximal Marginal Relevance (MMR) diversity re-ranking.

    When enabled, the fused candidate list is re-ordered to penalize chunks too
    similar to already-selected ones, trading some relevance for diversity.
    When disabled (the default), candidates keep their pure-relevance order.

    Attributes:
        enabled: Whether to apply MMR diversity re-ordering.
        diversity: 0.0 = pure relevance, 1.0 = pure diversity.
        candidates_limit: Pool size considered before MMR selection.
    """

    enabled: bool = Field(default=False, description="Apply MMR diversity re-ordering.")
    diversity: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="0.0 = pure relevance, 1.0 = pure diversity.",
    )
    candidates_limit: int = Field(
        default=100, ge=1,
        description="Pool size considered before MMR selection.",
    )


class RetrieveConfig(BaseModel):
    """
    Core retrieval tuning — fusion, candidate sizing, thresholds, and per-field weights.

    Every field defaults to the historical hard-coded value, so an absent or empty
    ``retrieve`` block reproduces the pre-existing behavior exactly (weighted RRF with
    k=60, candidate_limit = max(top_k*3, 20), all vectors, no score threshold).

    Attributes:
        vector_mode: Which named vectors to query — "hybrid" (dense + sparse),
            "dense" (semantic only), or "sparse" (keyword/BM25 only).
        fusion: Fusion method — "rrf" (reciprocal rank) or "dbsf" (distribution-based score).
        rrf_k: RRF rank constant (larger → flatter rank influence).
        candidate_multiplier: candidate_limit = max(top_k * this, min_candidates).
        min_candidates: Floor for candidate_limit regardless of top_k.
        score_threshold: Per-vector minimum similarity; None disables the cutoff.
        field_weights: Per-field fusion weight (applies to that field's dense + sparse
            vectors); missing field → weight 1.0.
        content_dense_weight: Fusion weight for the chunk-body dense vector.
        content_sparse_weight: Fusion weight for the chunk-body BM25 vector.
        grouping: Document-level grouping settings.
        mmr: MMR diversity re-ranking settings.
    """

    vector_mode: Literal["hybrid", "dense", "sparse"] = Field(
        default="hybrid",
        description="Vectors to query: hybrid (both), dense (semantic), or sparse (keyword).",
    )
    fusion: Literal["rrf", "dbsf"] = Field(
        default="rrf",
        description="Fusion method: rrf (reciprocal rank) or dbsf (distribution-based score).",
    )
    rrf_k: int = Field(default=60, ge=1, description="RRF rank constant.")
    candidate_multiplier: int = Field(
        default=3, ge=1,
        description="candidate_limit = max(top_k * multiplier, min_candidates).",
    )
    min_candidates: int = Field(
        default=20, ge=1, description="Floor for candidate_limit."
    )
    score_threshold: float | None = Field(
        default=None, description="Per-vector minimum similarity score; None disables."
    )
    field_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Per-field fusion weight (applies to dense + sparse vectors of that field).",
    )
    content_dense_weight: float = Field(
        default=1.0, ge=0.0, description="Fusion weight for the chunk-body dense vector."
    )
    content_sparse_weight: float = Field(
        default=1.0, ge=0.0, description="Fusion weight for the chunk-body BM25 vector."
    )
    grouping: GroupingConfig = Field(
        default_factory=GroupingConfig, description="Document-level grouping settings."
    )
    mmr: MmrConfig = Field(
        default_factory=MmrConfig, description="MMR diversity re-ranking settings."
    )


class SearchConfig(BaseModel):
    """
    Root search pipeline configuration.

    Composes retrieval tuning + query transform + rerank settings.  Stored inside
    the collection's pipeline JSONB column as ``pipeline.search``.  Defaults produce
    behavior identical to the pre-P7 search path (no transform, no rerank, weighted
    RRF retrieval with the historical constants).

    Attributes:
        retrieve: Core retrieval tuning (fusion, candidates, thresholds, weights).
        query_transform: Query expansion / rewriting settings.
        rerank: Cross-encoder reranking settings.
    """

    retrieve: RetrieveConfig = Field(
        default_factory=RetrieveConfig,
        description="Core retrieval tuning (fusion, candidate sizing, thresholds, weights).",
    )
    query_transform: QueryTransformConfig = Field(
        default_factory=QueryTransformConfig,
        description="Query transformation settings (rewrite / HyDE / multi-query).",
    )
    rerank: RerankConfig = Field(
        default_factory=RerankConfig,
        description="Cross-encoder reranking settings.",
    )

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SearchConfig:
        """
        Build a SearchConfig from a (possibly empty/partial) JSON dict.

        Args:
            raw (dict | None): Serialized search config (subset of collection.pipeline jsonb).

        Returns:
            SearchConfig: Parsed config with defaults filled in.
        """
        if not raw:
            return cls()
        return cls.model_validate(raw)
