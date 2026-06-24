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
from common_libs.config.pipeline.stages.search_config import SearchConfig
from common_libs.providers.embed.base import EmbedProvider
from common_libs.providers.llm.base import LLMProvider
from common_libs.providers.rerank.base import RerankProvider
from common_libs.search.field_index import RetrievalTuning
from libs.search.hybrid.models import DocumentGroup, SearchOutcome, SearchResult
from libs.search.hybrid.service import HybridSearchService

# ====== Local Project Imports ======
from .post import SearchPostProcessor
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

        # Resolve the runtime retrieval tuning once (fusion / candidates / threshold / weights)
        self._tuning = RetrievalTuning.from_config(getattr(config, "retrieve", None))

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
    ) -> SearchOutcome:
        """
        Execute the full search pipeline and return the ranked results (+ optional groups).

        Steps:
        1. Query transform — produces one or more query variants.
        2. Retrieval — fetch candidates from Qdrant (candidate_k when reranking, else top_k).
        3. Multi-query fusion — RRF across variant result sets when multiple variants.
        4. Rerank — cross-encoder re-scoring (when enabled).
        5. MMR diversity re-ranking (when enabled).
        6. Document grouping (when enabled) — collapse chunks into top documents.

        Args:
            query (str): User search query.
            top_k (int): Maximum results (chunks, or document groups when grouping is on).
            session (AsyncSession): Active Postgres session for chunk hydration.
            collection_name (str): Qdrant collection name (== Postgres collection id string).
            payload_filter (dict | None): Optional Qdrant payload filter.
            metadata_fields (list | None): Metadata schema for per-field vector weights.
            weight_overrides (dict[str, float] | None): Per-vector weight overrides.

        Returns:
            SearchOutcome: Flat ranked results + optional document groups.
        """
        # 1. Query transform — may produce multiple variants for multi-query retrieval
        variants = await self._transform.run(query)

        # 2. Candidate pool size: enough to feed rerank / MMR / grouping post-steps
        candidate_k = self._pool_size(top_k)

        # 3. Retrieve — single or multi-query path
        candidates = await self._retrieve(
            variants, candidate_k, session, collection_name,
            payload_filter, metadata_fields, weight_overrides,
        )

        # 4. Rerank (if enabled)
        if self._rerank_stage is not None:
            candidates = await self._rerank_stage.run(query=query, results=candidates)

        # 5. MMR diversity re-ranking (if enabled)
        candidates = await self._apply_mmr(query, candidates, collection_name, top_k)

        # 6. Document grouping (if enabled) → groups + flattened flat list
        return self._finalize(candidates, top_k)

    async def _retrieve(
        self,
        variants: list[str],
        candidate_k: int,
        session: AsyncSession,
        collection_name: str,
        payload_filter: dict | None,
        metadata_fields: list[Any] | None,
        weight_overrides: dict[str, float] | None,
    ) -> list[SearchResult]:
        """Run single- or multi-query retrieval and return the fused candidate list."""
        if len(variants) == 1:
            return await self._retrieval.search(
                collection_name=collection_name, query=variants[0], top_k=candidate_k,
                session=session, payload_filter=payload_filter, metadata_fields=metadata_fields,
                weight_overrides=weight_overrides, embed_provider=self._embed, tuning=self._tuning,
            )
        result_lists = await asyncio.gather(*[
            self._retrieval.search(
                collection_name=collection_name, query=variant, top_k=candidate_k,
                session=session, payload_filter=payload_filter, metadata_fields=metadata_fields,
                weight_overrides=weight_overrides, embed_provider=self._embed, tuning=self._tuning,
            )
            for variant in variants
        ])
        return _rrf_fuse(result_lists, k=self._tuning.rrf_k)[:candidate_k]

    def _pool_size(self, top_k: int) -> int:
        """
        Compute how many candidates to retrieve before post-processing.

        Reranking, MMR, and grouping each need a larger pool than the final top_k.

        Args:
            top_k (int): Final result count requested.

        Returns:
            int: Candidate pool size.
        """
        # Always retrieve at least top_k; reranking widens the pool to candidate_k.
        pool = top_k
        if self._rerank_stage:
            pool = max(pool, self._config.rerank.candidate_k)
        grouping = self._config.retrieve.grouping
        mmr = self._config.retrieve.mmr
        if grouping.enabled:
            pool = max(pool, top_k * grouping.group_size)
        if mmr.enabled:
            pool = max(pool, mmr.candidates_limit)
        return pool

    async def _apply_mmr(
        self, query: str, candidates: list[SearchResult], collection_name: str, top_k: int
    ) -> list[SearchResult]:
        """
        Re-rank candidates with MMR diversity when enabled; otherwise return them unchanged.

        Fetches the query + candidate dense vectors and delegates to SearchPostProcessor.
        The selection limit stays wide enough for downstream grouping.

        Args:
            query (str): The user query (re-embedded for relevance scoring).
            candidates (list[SearchResult]): Ranked candidates from retrieval/rerank.
            collection_name (str): Qdrant collection name.
            top_k (int): Final result count requested.

        Returns:
            list[SearchResult]: MMR-reordered candidates (or unchanged when MMR is off).
        """
        mmr = self._config.retrieve.mmr
        if not mmr.enabled or not candidates:
            return candidates
        # Keep enough items for grouping to still form top_k groups after diversification.
        limit = top_k * self._config.retrieve.grouping.group_size if self._config.retrieve.grouping.enabled else top_k
        query_vec = await self._retrieval.embed_query_dense(query, embed_provider=self._embed)
        vecs = await self._retrieval.fetch_dense_vectors(
            collection_name, [c.chunk_id for c in candidates]
        )
        items = [(c, vecs.get(c.chunk_id, [])) for c in candidates]
        return SearchPostProcessor.mmr_reorder(query_vec, items, mmr.diversity, limit=max(limit, top_k))

    def _finalize(self, candidates: list[SearchResult], top_k: int) -> SearchOutcome:
        """
        Apply grouping (when enabled) and trim to top_k; build the SearchOutcome.

        Args:
            candidates (list[SearchResult]): Post-rerank/MMR candidate list.
            top_k (int): Final count of chunks (no grouping) or documents (grouping).

        Returns:
            SearchOutcome: Flat results + optional document groups.
        """
        grouping = self._config.retrieve.grouping
        if not grouping.enabled:
            return SearchOutcome(results=candidates[:top_k], groups=None)
        groups: list[DocumentGroup] = SearchPostProcessor.group_by_document(
            candidates, group_size=grouping.group_size, max_groups=top_k
        )
        flat = [c for g in groups for c in g.chunks]
        return SearchOutcome(results=flat, groups=groups)

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
        candidate_k = self._pool_size(top_k)

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
            tuning=self._tuning,
        )

        # 3. Rerank candidates when enabled
        candidates = debug_data.get("results", [])
        if self._rerank_stage is not None and candidates:
            candidates = await self._rerank_stage.run(query=query, results=candidates)

        # 4. MMR diversity + document grouping (same post-steps as run())
        candidates = await self._apply_mmr(query, candidates, collection_name, top_k)
        outcome = self._finalize(candidates, top_k)
        debug_data["results"] = outcome.results
        debug_data["groups"] = outcome.groups

        # 5. Attach pipeline-level debug info
        grouping = self._config.retrieve.grouping
        mmr = self._config.retrieve.mmr
        debug_data["pipeline"] = {
            "query_variants": variants,
            "strategy": self._config.query_transform.strategy,
            "rerank_enabled": self._rerank_stage is not None,
            "grouping_enabled": grouping.enabled,
            "mmr_enabled": mmr.enabled,
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
