# ====== Code Summary ======
# ProviderRegistry — resolves a declarative PipelineConfig into concrete pipeline stages
# (spec §6: locality → provider → device).
#
# Every provider is a ProviderSpec (id + params).  Params supplied in the request (e.g. a
# Mistral API key typed into the playground) take precedence over deployment env defaults —
# this is what lets a user wire an external provider on the fly.
#
# The describe-surface (describe_stages, _params_from_instance, _auto_providers) lives in
# DescribeSurface (describe.py).  Availability probes live in AvailabilityProbes (availability.py).
# The 5 chain builders live in ChainBuilderHelpers (chain_builders.py).  ProviderRegistry
# inherits DescribeSurface and delegates chain construction + reachability checks to those.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from common_libs.providers.chain import Chain
from common_libs.providers.chain_gate import ChainGateConfig

# ====== Internal Project Imports ======
from common_libs.config.pipeline import (
    EnrichConfig,
    PipelineConfig,
    ProviderSpec,
)
from common_libs.storage.s3.client import S3Client
from common_libs.pipeline.caches.provider_cache import ProviderCallCache
from common_libs.pipeline.stages.s2_enrich import S2EnrichStage
from common_libs.pipeline.stages.s4_chunk import S4ChunkStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage

# ====== Local Project Imports ======
from .chain_builders import ChainBuilderHelpers
from .chunk_stage_assembler import ChunkStageAssembler
from .describe import DescribeSurface
from .resolved import ResolvedStages


class ProviderRegistry(DescribeSurface, LoggerClass):
    """
    Resolves PipelineConfig → instantiated stages, and describes the configurable surface.

    Shared infrastructure (S3, provider cache) and deployment credential/endpoint defaults
    come from construction; per-run provider choices + params come from the PipelineConfig.

    Resolution logic lives directly on this class.  The describe surface (describe_stages,
    _auto_providers, _params_from_instance) is contributed by DescribeSurface.  Chain
    construction is delegated to ChainBuilderHelpers; network reachability probes to
    AvailabilityProbes.
    """

    def __init__(
        self,
        s3: S3Client,
        provider_cache: ProviderCallCache,
        runtime_config: Any,
    ) -> None:
        """
        Initialize the registry with shared infrastructure and deployment defaults.

        Args:
            s3 (S3Client): Object store client (figure crops live here).
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            runtime_config (Any): RUNTIME_CONFIG — fallback credentials/endpoints used when
                a ProviderSpec omits a param, plus the basis for availability checks.
        """
        LoggerClass.__init__(self)
        self._s3 = s3
        self._provider_cache = provider_cache
        self._cfg = runtime_config

    # ─── Stage resolution ──────────────────────────────────────────────────────

    def build_stages(self, config: PipelineConfig) -> ResolvedStages:
        """
        Resolve a PipelineConfig into concrete pipeline stages.

        Validates each requested provider against availability (credential-aware) and raises
        ProviderUnavailableError (→ HTTP 422) when a knob cannot be honored.

        Args:
            config (PipelineConfig): The per-run pipeline configuration.

        Returns:
            ResolvedStages: parse_chain + S2/S4/S5 stages — always all present (S6 is owned
                by the caller's infra as it holds a live Qdrant connection).

        Raises:
            ProviderUnavailableError: When a requested provider cannot run here.
        """
        parse_chain = self._build_parser_chain(config.parse.chain, config.parse.gate)
        s2 = self._build_s2(config.enrich)
        s4 = ChunkStageAssembler.build_chunk_stage(self._cfg, config.chunk)
        s5 = S5ContextualizeStage(config=config.contextualize)

        return ResolvedStages(parse_chain=parse_chain, s2=s2, s4=s4, s5=s5)

    def build_enrich_and_chunk_stages(
        self,
        config: PipelineConfig,
    ) -> tuple[S2EnrichStage, S4ChunkStage, S5ContextualizeStage]:  # type: ignore[name-defined]
        """
        Build S2, S4, S5 from a typed PipelineConfig — for the startup default stack.

        Called by entrypoint.py and worker.py to replace the 9 direct provider
        instantiations with a single config-driven call.  S6 is built per-job by
        StageEngine._build_s6_from_config() and is excluded here.

        Args:
            config (PipelineConfig): Fully typed pipeline config (from build_default_pipeline).

        Returns:
            tuple: (S2EnrichStage, S4ChunkStage, S5ContextualizeStage) ready to inject.
        """
        # 1. Build S2 (every sub-stage is now a Chain[T, R]).
        s2 = self._build_s2(config.enrich)

        # 2. Build S4 splitter from config
        splitter = ChunkStageAssembler.build_splitter(self._cfg, config.chunk.split_method)
        s4 = S4ChunkStage(splitter=splitter)

        # 3. S5 carries its own contextualization config (header template / separators).
        s5 = S5ContextualizeStage(config=config.contextualize)

        return s2, s4, s5

    # ─── Internal stage builders ───────────────────────────────────────────────

    def _build_s2(self, enrich: EnrichConfig) -> S2EnrichStage:
        """
        Wire S2 with classifier / OCR / VLM chains from the enrichment config.

        Args:
            enrich (EnrichConfig): Enrichment configuration block (classifier chain,
                OCR chain, VLM chain, gates, and budget cap).

        Returns:
            S2EnrichStage: Fully wired enrichment stage ready for the pipeline.
        """
        classifier_chain = self._build_classifier_chain(
            enrich.classifier_chain, enrich.classifier_gate,
        )
        ocr_chain = self._build_ocr_chain(enrich.ocr_chain, enrich.ocr_gate)
        vlm_chain = self._build_vlm_chain(enrich.vlm_chain, enrich.vlm_gate)
        return S2EnrichStage(
            classifier_chain=classifier_chain,
            ocr_chain=ocr_chain,
            vlm_chain=vlm_chain,
            s3=self._s3,
            provider_cache=self._provider_cache,
            max_budget_usd=enrich.max_budget_usd,
        )

    # ─── Chain builders (thin delegators to ChainBuilderHelpers) ────────────────

    def _build_parser_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """Build the parser chain (delegates to ChainBuilderHelpers)."""
        return ChainBuilderHelpers.build_parser_chain(self._cfg, specs, gate_cfg)

    def _build_classifier_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """Build the figure-classifier chain (delegates to ChainBuilderHelpers)."""
        return ChainBuilderHelpers.build_classifier_chain(self._cfg, specs, gate_cfg)

    def _build_ocr_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any] | None:
        """Build the OCR chain (delegates to ChainBuilderHelpers)."""
        return ChainBuilderHelpers.build_ocr_chain(self._cfg, specs, gate_cfg)

    def _build_vlm_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any] | None:
        """Build the VLM chain (delegates to ChainBuilderHelpers)."""
        return ChainBuilderHelpers.build_vlm_chain(self._cfg, specs, gate_cfg)

    def _build_embed_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
        sparse_spec: Any = None,
    ) -> Chain[Any, Any]:
        """Build the S6 embed chain (delegates to ChainBuilderHelpers).

        ``sparse_spec`` (optional) sources sparse vectors from a separate backend — see
        ChainBuilderHelpers.build_embed_chain.
        """
        return ChainBuilderHelpers.build_embed_chain(self._cfg, specs, gate_cfg, sparse_spec)

    def build_search_pipeline(
        self,
        pipeline_dict: dict | None,
        retrieval: "HybridSearchService",
    ) -> "SearchPipelineEngine":
        """
        Build a SearchPipelineEngine from a collection's stored pipeline config.

        Derives the embed provider from pipeline.embed.chain[0] (same model used during
        S6 indexing) and optionally wires a reranker and LLM when the search config
        requests them.  Defaults (strategy="none", rerank.enabled=False) produce identical
        results to the pre-P7 direct HybridSearchService.search() call.

        Args:
            pipeline_dict (dict | None): Raw JSON pipeline dict stored on the collection.
                None or empty falls back to the default PipelineConfig.
            retrieval (HybridSearchService): Shared retrieval service -- passed through, not
                stored on ProviderRegistry to avoid circular ownership.

        Returns:
            SearchPipelineEngine: Configured search pipeline ready to call .run() / .run_debug().

        Raises:
            ValueError: If a requested provider (reranker, LLM) cannot be built from config.
        """
        # Lazy imports to honour the layer DAG: pipeline(3) imports from search(2) and providers(1).
        # These must not appear at module level or they create circular dependency cycles.
        from libs.search.pipeline import SearchPipelineEngine

        # 1. Deserialize the stored pipeline config (or fall back to defaults when absent)
        pipeline = PipelineConfig.from_dict(pipeline_dict)

        # 2. Build embed provider -- must match the model(s) used during S6 indexing.
        #    When a separate sparse backend is configured, the query is embedded by a composite
        #    (dense from chain[0], sparse from the sparse backend) so both named-vector families
        #    can be queried — exactly mirroring how the documents were indexed.
        embed_spec = pipeline.embed.chain[0]
        embed_provider = embed_spec.merge_defaults(self._cfg).build()
        sparse_spec = getattr(pipeline.embed, "sparse", None)
        if sparse_spec is not None:
            from common_libs.providers.embed.composite import CompositeEmbedProvider
            sparse_provider = sparse_spec.merge_defaults(self._cfg).build()
            embed_provider = CompositeEmbedProvider(dense=embed_provider, sparse=sparse_provider)

        # 3. Optionally build reranker from pipeline.search.rerank.chain[0]
        reranker = None
        if pipeline.search.rerank.enabled and pipeline.search.rerank.chain:
            rerank_spec = pipeline.search.rerank.chain[0]
            reranker = rerank_spec.merge_defaults(self._cfg).build()

        # 4. Optionally build LLM from pipeline.search.query_transform.llm
        llm = None
        qt = pipeline.search.query_transform
        if qt.strategy != "none" and qt.llm is not None:
            llm = qt.llm.merge_defaults(self._cfg).build()

        # 5. Assemble and return the search pipeline engine
        return SearchPipelineEngine(
            config=pipeline.search,
            embed_provider=embed_provider,
            retrieval=retrieval,
            reranker=reranker,
            llm=llm,
        )
