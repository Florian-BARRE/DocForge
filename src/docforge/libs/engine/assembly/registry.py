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
# ProviderRegistry inherits DescribeSurface and delegates reachability checks to AvailabilityProbes.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from libs.capabilities.chain import Chain
from libs.capabilities.chain_gate import ChainGate, ChainGateConfig
from libs.capabilities.classifier.local.vit_onnx_config import VitOnnxConfig
from libs.capabilities.ocr.external.mistral_ocr_config import MistralOcrConfig
from libs.capabilities.ocr.local.paddle_ocr_config import PaddleOcrConfig
from libs.capabilities.parser.local.docling import DoclingConfig
from libs.capabilities.vlm.external.openai_compat_config import OpenAIVlmConfig
from libs.capabilities.vlm.local.openai_compat_config import LocalVlmConfig

# ====== Internal Project Imports ======
from libs.core.contracts.pipeline_config import (
    ChunkConfig,
    EnrichConfig,
    PipelineConfig,
    ProviderSpec,
    SplitMethodConfig,
)
from libs.data.storage.s3.client import S3Client
from libs.engine.provider_cache import ProviderCallCache
from libs.engine.stages.chunking import (
    SectionSplitter,
    SemanticParams,
)
from libs.engine.stages.s2_enrich import S2EnrichStage
from libs.engine.stages.s4_chunk import S4ChunkStage
from libs.engine.stages.s5_contextualize import S5ContextualizeStage

# ====== Local Project Imports ======
from .availability import AvailabilityProbes, ProviderUnavailableError
from .describe import DescribeSurface


@dataclass(slots=True)
class ResolvedStages:
    """
    Concrete pipeline stages resolved from a PipelineConfig for a single run.

    S0/S6 are handled outside this struct (S0 is constant; S6 owns a live Qdrant connection
    managed by the worker/app, not the registry).

    Attributes:
        parse_chain (Chain[ParserProvider, DocumentIR]): Ordered parser chain for S1.
        s2 (S2EnrichStage): Enrichment stage — always present (pipeline is fixed S0→S6).
        s4 (S4ChunkStage): Chunking stage — always present.
        s5 (S5ContextualizeStage): Contextualization stage — always present.
    """

    parse_chain: Chain[Any, Any]
    s2: S2EnrichStage
    s4: S4ChunkStage
    s5: S5ContextualizeStage

    @property
    def parser(self) -> Any:
        """Backward-compat shim — returns the FIRST provider in the parse chain."""
        return self.parse_chain.providers[0] if self.parse_chain.providers else None


class ProviderRegistry(DescribeSurface, LoggerClass):
    """
    Resolves PipelineConfig → instantiated stages, and describes the configurable surface.

    Shared infrastructure (S3, provider cache) and deployment credential/endpoint defaults
    come from construction; per-run provider choices + params come from the PipelineConfig.

    Resolution logic lives directly on this class.  The describe surface (describe_stages,
    _auto_providers, _params_from_instance) is contributed by DescribeSurface.  Network
    reachability probes are delegated to AvailabilityProbes.
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
        s4 = self._build_chunk_stage(config.chunk)
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
        splitter = self._build_splitter(config.chunk.split_method)
        s4 = S4ChunkStage(splitter=splitter)

        # 3. S5 carries its own contextualization config (header template / separators).
        s5 = S5ContextualizeStage(config=config.contextualize)

        return s2, s4, s5

    # ─── Internal stage builders ───────────────────────────────────────────────

    def _build_chunk_stage(self, chunk: ChunkConfig) -> S4ChunkStage:
        """
        Build the S4 chunking stage from config: split method + atomic policy + mode.

        Args:
            chunk (ChunkConfig): The chunking configuration block.

        Returns:
            S4ChunkStage: Wired chunking stage.

        Raises:
            ProviderUnavailableError: When the semantic method is requested but TEI is unreachable.
        """
        # 1. Resolve the intra-section split method (the decision-tree-by-method)
        splitter = self._build_splitter(chunk.split_method)

        # 2. Wire the heading skeleton + atomic policy + mode around it
        return S4ChunkStage(
            splitter=splitter,
            heading_rules=chunk.heading_rules,
            reinject_breadcrumb=chunk.reinject_breadcrumb,
            merge_short_sections=chunk.merge_short_sections,
            atomic=chunk.atomic,
            cross_references=chunk.cross_references,
            hierarchical=chunk.hierarchical,
        )

    def _build_splitter(self, spec: SplitMethodConfig) -> SectionSplitter:
        """
        Instantiate the requested intra-section split method from its typed config.

        Merges deployment defaults into the typed config then delegates to build().
        Semantic split requires a reachable TEI endpoint and is checked before build().

        Args:
            spec (SplitMethodConfig): Typed split method config (discriminated union).

        Returns:
            SectionSplitter: Wired splitter.

        Raises:
            ProviderUnavailableError: When semantic is requested but TEI is unreachable.
        """
        # 1. Merge deployment defaults into the typed config (e.g. TEI_BASE_URL for semantic)
        merged = spec.merge_defaults(self._cfg)

        # 2. Semantic split now accepts any embed provider — only a LOCAL base_url is probed
        # for reachability; cloud HTTPS endpoints are assumed reachable and will report an
        # actionable error at the first ``embed()`` call if they aren't.
        if isinstance(merged, SemanticParams):
            embed_cfg = getattr(merged, "embed", None)
            embed_url = getattr(embed_cfg, "base_url", "") or "" if embed_cfg else ""
            if embed_url and not embed_url.startswith("https://"):
                if not AvailabilityProbes.endpoint_reachable(embed_url):
                    raise ProviderUnavailableError(
                        "split_method", "semantic",
                        f"Semantic chunking needs a reachable embed endpoint (got {embed_url!r}).",
                    )

        # 3. Delegate instantiation to the typed config (build() knows its own splitter)
        return merged.build()

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

    # ─── Chain builders (one per stage; share the same Chain primitive) ──────

    def _build_parser_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """
        Instantiate the parser providers in declaration order and wrap them in a Chain.

        Args:
            specs (list[ProviderSpec]): Typed parser configs (currently only DoclingConfig).
            gate_cfg (ChainGateConfig): Escalation policy applied after each attempt.

        Returns:
            Chain[ParserProvider, DocumentIR]: Wired parser chain.

        Raises:
            ProviderUnavailableError: When a requested parser cannot be instantiated.
        """
        if not specs:
            raise ProviderUnavailableError(
                "parse", "none", "At least one parser must be configured.",
            )
        built: list[Any] = []
        for spec in specs:
            if not isinstance(spec, DoclingConfig):
                raise ProviderUnavailableError(
                    "parse", getattr(spec, "id", str(spec)),
                    "Only the Docling backend is installed in this deployment.",
                )
            merged = spec.merge_defaults(self._cfg)
            built.append(merged.build())
        return Chain(stage="parse", providers=built, gate=ChainGate(gate_cfg))

    def _build_classifier_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """Build the figure-classifier chain (ViT and/or LayoutLabels)."""
        if not specs:
            raise ProviderUnavailableError(
                "classifier", "none", "At least one classifier must be configured.",
            )
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(self._cfg)
            if isinstance(merged, VitOnnxConfig):
                if not os.path.exists(merged.model_path):
                    raise ProviderUnavailableError(
                        "classifier", "vit_onnx",
                        f"ONNX model not found at {merged.model_path}.",
                    )
            built.append(merged.build())
        return Chain(stage="classifier", providers=built, gate=ChainGate(gate_cfg))

    def _build_ocr_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any] | None:
        """
        Build the OCR escalation chain.

        Returns None when no OCR providers are configured — the caller must guard against
        that case and skip OCR routing.
        """
        if not specs:
            return None
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(self._cfg)
            if isinstance(merged, PaddleOcrConfig):
                try:
                    import paddleocr  # noqa: F401
                except Exception:
                    raise ProviderUnavailableError(
                        "ocr", "paddle_ocr", "paddleocr package is not installed.",
                    )
            elif isinstance(merged, MistralOcrConfig):
                if not merged.api_key:
                    raise ProviderUnavailableError(
                        "ocr", "mistral_ocr",
                        "No API key — fill it in the playground or set MISTRAL_OCR_API_KEY.",
                    )
            else:
                raise ProviderUnavailableError(
                    "ocr", getattr(merged, "id", str(merged)), "Unknown OCR provider id.",
                )
            built.append(merged.build())
        return Chain(stage="ocr", providers=built, gate=ChainGate(gate_cfg))

    def _build_vlm_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any] | None:
        """
        Build the VLM escalation chain.

        Returns None when ``specs`` is empty — disables VLM enrichment entirely.
        """
        if not specs:
            return None
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(self._cfg)
            if isinstance(merged, LocalVlmConfig):
                if not merged.base_url:
                    raise ProviderUnavailableError(
                        "vlm", "openai_compat", "No VLM base URL configured.",
                    )
            elif isinstance(merged, OpenAIVlmConfig):
                if not merged.base_url:
                    raise ProviderUnavailableError(
                        "vlm", "openai", "No VLM base URL configured.",
                    )
                if not merged.api_key:
                    raise ProviderUnavailableError(
                        "vlm", "openai",
                        "No API key — fill it in the playground or set VLM_API_KEY.",
                    )
            else:
                raise ProviderUnavailableError(
                    "vlm", getattr(merged, "id", str(merged)),
                    "Unknown VLM provider id. Valid ids: 'openai_compat' (local), 'openai' (cloud).",
                )
            built.append(merged.build())
        return Chain(stage="vlm", providers=built, gate=ChainGate(gate_cfg))

    def _build_embed_chain(
        self,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """Build the S6 embed chain from typed EmbedProviderConfig specs."""
        if not specs:
            raise ProviderUnavailableError(
                "embed", "none", "At least one embed provider must be configured.",
            )
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(self._cfg)
            built.append(merged.build())
        return Chain(stage="embed", providers=built, gate=ChainGate(gate_cfg))
