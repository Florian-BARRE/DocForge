# ====== Code Summary ======
# build_search_pipeline — assembles a SearchPipelineEngine from a collection's stored
# pipeline config. Relocated OUT of the common ProviderRegistry: assembling a search
# pipeline is an APP concern (it wires the app-dedicated SearchPipelineEngine), so it must
# not live in shared code. Keeping it here removes the last common→app reference.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig

# ====== Local Project Imports ======
from .hybrid.service import HybridSearchService
from .pipeline import SearchPipelineEngine


def build_search_pipeline(
    pipeline_dict: dict | None,
    retrieval: HybridSearchService,
    runtime_config: Any,
) -> SearchPipelineEngine:
    """
    Build a SearchPipelineEngine from a collection's stored pipeline config.

    Derives the embed provider from pipeline.embed.chain[0] (same model used during S6
    indexing) and optionally wires a reranker and LLM when the search config requests them.
    Defaults (strategy="none", rerank.enabled=False) produce identical results to the
    pre-P7 direct HybridSearchService.search() call.

    Args:
        pipeline_dict (dict | None): Raw JSON pipeline dict stored on the collection.
            None or empty falls back to the default PipelineConfig.
        retrieval (HybridSearchService): Shared retrieval service.
        runtime_config (Any): RUNTIME_CONFIG — supplies provider defaults via merge_defaults().

    Returns:
        SearchPipelineEngine: Configured search pipeline ready to call .run() / .run_debug().

    Raises:
        ValueError: If a requested provider (reranker, LLM) cannot be built from config.
    """
    # 1. Deserialize the stored pipeline config (or fall back to defaults when absent)
    pipeline = PipelineConfig.from_dict(pipeline_dict)

    # 2. Build embed provider — must match the model(s) used during S6 indexing.
    #    When a separate sparse backend is configured, the query is embedded by a composite
    #    (dense from chain[0], sparse from the sparse backend) so both named-vector families
    #    can be queried — exactly mirroring how the documents were indexed.
    embed_spec = pipeline.embed.chain[0]
    embed_provider = embed_spec.merge_defaults(runtime_config).build()
    sparse_spec = getattr(pipeline.embed, "sparse", None)
    if sparse_spec is not None:
        from common_libs.providers.embed import CompositeEmbedProvider

        sparse_provider = sparse_spec.merge_defaults(runtime_config).build()
        embed_provider = CompositeEmbedProvider(dense=embed_provider, sparse=sparse_provider)

    # 3. Optionally build reranker from pipeline.search.rerank.chain[0]
    reranker = None
    if pipeline.search.rerank.enabled and pipeline.search.rerank.chain:
        rerank_spec = pipeline.search.rerank.chain[0]
        reranker = rerank_spec.merge_defaults(runtime_config).build()

    # 4. Optionally build LLM from pipeline.search.query_transform.llm
    llm = None
    qt = pipeline.search.query_transform
    if qt.strategy != "none" and qt.llm is not None:
        llm = qt.llm.merge_defaults(runtime_config).build()

    # 5. Assemble and return the search pipeline engine
    return SearchPipelineEngine(
        config=pipeline.search,
        embed_provider=embed_provider,
        retrieval=retrieval,
        reranker=reranker,
        llm=llm,
    )


__all__ = ["build_search_pipeline"]
