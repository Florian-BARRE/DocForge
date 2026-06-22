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

        # Lazy imports to preserve the leaf constraint
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from libs.providers.llm.external.config import OpenAILLMConfig
        from libs.providers.llm.local.config import LocalLLMConfig

        union = Annotated[LocalLLMConfig | OpenAILLMConfig, _F(discriminator="id")]
        adapter = TypeAdapter(union)
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

        from libs.providers.rerank.external.config import CohereRerankConfig
        from libs.providers.rerank.local.config import BgeRerankerConfig

        union = Annotated[BgeRerankerConfig | CohereRerankConfig, _F(discriminator="id")]
        adapter = TypeAdapter(union)

        coerced = [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ]
        object.__setattr__(self, "chain", coerced)
        return self


class SearchConfig(BaseModel):
    """
    Root search pipeline configuration.

    Composes query transform + rerank settings.  Stored inside the collection's
    pipeline JSONB column as ``pipeline.search``.  Defaults produce behavior
    identical to the pre-P7 search path (no transform, no rerank).

    Attributes:
        query_transform: Query expansion / rewriting settings.
        rerank: Cross-encoder reranking settings.
    """

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
