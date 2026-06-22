# ====== Code Summary ======
# SearchPipelineEngine — orchestrates the full search pipeline:
#   query transform → multi-query retrieval → RRF fusion → optional rerank.
#
# The embed provider is always injected at construction from the collection's ingestion
# pipeline (pipeline.embed.chain[0]) to guarantee query vectors live in the same space
# as the indexed vectors.  The engine wraps HybridSearchService without modifying it.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.config.pipeline.stages.search_config import SearchConfig
from libs.providers.embed.base import EmbedProvider
from libs.providers.llm.base import LLMProvider
from libs.providers.rerank.base import RerankProvider
from libs.search.hybrid.models import SearchResult
from libs.search.hybrid.service import HybridSearchService

# ====== Local Project Imports ======
from .stages.q_transform import QueryTransformStage
from .stages.rerank import RerankStage


class SearchPipelineEngine(LoggerClass):
    """
    Orchestrates the full search pipeline: query transform → retrieval → rerank.

    The embed provider is injected at construction time, always derived from the
    collection's ingestion pipeline so query vectors match indexed vectors.

    When all optional stages are disabled (the default), the engine produces exactly
    the same results as calling HybridSearchService.search() directly — backward
    compatibility is guaranteed by the defaults in SearchConfig.

    Attributes:
        _config (SearchConfig): Pipeline configuration (transform + rerank settings).
        _embed (EmbedProvider): Query embedding provider (same as ingestion).
        _retrieval (HybridSearchService): Hybrid Qdrant+Postgres retrieval service.
        _reranker (RerankProvider | None): Cross-encoder provider (None = disabled).
        _llm (LLMProvider | None): LLM provider for query transform (None = passthrough).
        _transform (QueryTransformStage): Query transform stage instance.
        _rerank_stage (RerankStage | None): Rerank stage instance (None = disabled).
    """

    def __init__(
        self,
        config: SearchConfig,
        embed_provider: EmbedProvider,
        retrieval: HybridSearchService,
        reranker: RerankProvider | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        """
        Initialize the search pipeline engine.

        Args:
            config (SearchConfig): Search pipeline configuration.
            embed_provider (EmbedProvider): Query embedding provider (derived from ingestion config).
            retrieval (HybridSearchService): Hybrid search service.
            reranker (RerankProvider | None): Reranking provider (None = disabled).
            llm (LLMProvider | None): LLM for query transform (None = passthrough).
        """
        LoggerClass.__init__(self)
        self._config = config
        self._embed = embed_provider
        self._retrieval = retrieval
        self._reranker = reranker
        self._llm = llm

        # Instantiate sub-stages from injected providers
        self._transform = QueryTransformStage(config=config.query_transform, llm=llm)
        self._rerank_stage: RerankStage | None = (
            RerankStage(config=config.rerank, provider=reranker)
            if config.rerank.enabled and reranker is not None
            else None
        )

        self.logger.info(
            f"SearchPipelineEngine: strategy={config.query_transform.strategy} "
            f"rerank={config.rerank.enabled} "
            f"candidate_k={config.rerank.candidate_k if config.rerank.enabled else 'n/a'}"
        )

    async def run(
        self,
        query: str,
        top_k: int,
        session: AsyncSession,
        collection_name: str,
        payload_filter: dict | None = None,
        metadata_fields: list[Any] | None = None,
        weight_overrides: dict[str, float] | None = None,
    ) -> list[SearchResult]:
        """
        Execute the full search pipeline and return the top results.

        Steps:
        1. Query transform — produces one or more query variants.
        2. Retrieval — fetch candidates from Qdrant (candidate_k when reranking, else top_k).
        3. Multi-query fusion — RRF across variant result sets when multiple variants.
        4. Rerank — cross-encoder re-scoring and trimming to top_n (when enabled).

        Args:
            query (str): User search query.
            top_k (int): Maximum results to return.
            session (AsyncSession): Active Postgres session for chunk hydration.
            collection_name (str): Qdrant collection name (== Postgres collection id string).
            payload_filter (dict | None): Optional Qdrant payload filter.
            metadata_fields (list | None): Metadata schema for per-field vector weights.
            weight_overrides (dict[str, float] | None): Per-vector weight overrides.

        Returns:
            list[SearchResult]: Results ordered by descending relevance score.
        """
        # 1. Query transform — may produce multiple variants for multi-query retrieval
        variants = await self._transform.run(query)

        # 2. Determine how many candidates to retrieve
        candidate_k = self._config.rerank.candidate_k if self._rerank_stage else top_k

        # 3. Retrieve — single or multi-query path
        if len(variants) == 1:
            candidates = await self._retrieval.search(
                collection_name=collection_name,
                query=variants[0],
                top_k=candidate_k,
                session=session,
                payload_filter=payload_filter,
                metadata_fields=metadata_fields,
                weight_overrides=weight_overrides,
                embed_provider=self._embed,
            )
        else:
            # Multi-query: fetch candidates for each variant in parallel, then RRF-fuse
            result_lists = await asyncio.gather(*[
                self._retrieval.search(
                    collection_name=collection_name,
                    query=variant,
                    top_k=candidate_k,
                    session=session,
                    payload_filter=payload_filter,
                    metadata_fields=metadata_fields,
                    weight_overrides=weight_overrides,
                    embed_provider=self._embed,
                )
                for variant in variants
            ])
            candidates = _rrf_fuse(result_lists, k=60)[:candidate_k]

        # 4. Rerank (if enabled)
        if self._rerank_stage is not None:
            candidates = await self._rerank_stage.run(query=query, results=candidates)

        return candidates[:top_k]

    async def run_debug(
        self,
        query: str,
        top_k: int,
        session: AsyncSession,
        collection_name: str,
        payload_filter: dict | None = None,
        metadata_fields: list[Any] | None = None,
        weight_overrides: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the search pipeline with detailed debug output.

        Returns the same structure as HybridSearchService.search_debug() with
        additional pipeline metadata (query variants, rerank scores when applicable).

        Args:
            query (str): User search query.
            top_k (int): Maximum results to return.
            session (AsyncSession): Active Postgres session.
            collection_name (str): Qdrant collection name.
            payload_filter (dict | None): Optional Qdrant payload filter.
            metadata_fields (list | None): Metadata schema for per-field vector weights.
            weight_overrides (dict[str, float] | None): Per-vector weight overrides.

        Returns:
            dict: Debug data including query variants, retrieval internals, and rerank scores.
        """
        # 1. Query transform
        variants = await self._transform.run(query)
        candidate_k = self._config.rerank.candidate_k if self._rerank_stage else top_k

        # 2. Debug retrieval — always use the first (or only) variant for Qdrant debug path
        debug_data = await self._retrieval.search_debug(
            collection_name=collection_name,
            query=variants[0],
            top_k=candidate_k,
            session=session,
            payload_filter=payload_filter,
            metadata_fields=metadata_fields,
            weight_overrides=weight_overrides,
            embed_provider=self._embed,
        )

        # 3. Rerank candidates when enabled
        candidates = debug_data.get("results", [])
        if self._rerank_stage is not None and candidates:
            candidates = await self._rerank_stage.run(query=query, results=candidates)
            debug_data["results"] = candidates[:top_k]
        else:
            debug_data["results"] = candidates[:top_k]

        # 4. Attach pipeline-level debug info
        debug_data["pipeline"] = {
            "query_variants": variants,
            "strategy": self._config.query_transform.strategy,
            "rerank_enabled": self._rerank_stage is not None,
        }

        return debug_data


def _rrf_fuse(result_lists: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
    """
    Reciprocal Rank Fusion across multiple retrieval result lists.

    Computes RRF score for each chunk: score(d) = Σ_i 1 / (k + rank_i(d))
    where rank_i(d) is the 1-indexed position of document d in list i.
    Deduplicates by chunk_id; keeps the SearchResult from the highest-scoring occurrence.

    Args:
        result_lists (list[list[SearchResult]]): Per-variant retrieval results.
        k (int): RRF constant (default 60 — standard value from the original paper).

    Returns:
        list[SearchResult]: Deduplicated results sorted by descending RRF score.
    """
    rrf_scores: dict[str, float] = {}
    best_result: dict[str, SearchResult] = {}

    for result_list in result_lists:
        for rank_zero, result in enumerate(result_list):
            chunk_id = result.chunk_id
            contribution = 1.0 / (k + rank_zero + 1)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + contribution
            # Keep the SearchResult instance from the first (highest-ranked) occurrence
            if chunk_id not in best_result:
                best_result[chunk_id] = result

    # Sort by descending RRF score
    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
    return [best_result[cid] for cid in sorted_ids]
