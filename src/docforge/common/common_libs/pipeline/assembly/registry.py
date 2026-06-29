# ====== Code Summary ======
# ProviderRegistry — provides the per-stage inner builders (parser / S2 / metagen / embed chains)
# from a declarative PipelineConfig (spec §6: locality → provider → device), which the dynamic
# stage assembler (assembly.build_pipeline) composes into the pipeline; also describes the surface.
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

from common_libs.pipeline.bricks.chain import Chain
from common_libs.pipeline.bricks.chain.gate import ChainGateConfig

# ====== Internal Project Imports ======
from common_libs.config.pipeline import (
    EnrichConfig,
    MetaGenConfig,
    ProviderSpec,
)
from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec
from common_libs.storage.s3.client import S3Client
from common_libs.pipeline.caches.provider_cache import ProviderCallCache
from common_libs.pipeline.stages.s2_enrich import S2EnrichStage
from common_libs.pipeline.stages.s5b_metagen import S5bMetagenStage

# ====== Local Project Imports ======
from .chain_builders import ChainBuilderHelpers
from .describe import DescribeSurface


class ProviderRegistry(DescribeSurface, LoggerClass):
    """
    Provides the per-stage inner builders from a PipelineConfig, and describes the configurable surface.

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

    # ─── Internal stage builders ───────────────────────────────────────────────

    def _build_s2(self, enrich: EnrichConfig) -> S2EnrichStage:
        """
        Wire S2 with classifier / OCR / VLM chains from the enrichment config.

        Args:
            enrich (EnrichConfig): Enrichment configuration block (classifier chain,
                OCR chain, VLM chain, and gates).

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
            chart_to_data=enrich.chart_to_data,
        )

    def _build_metagen(
        self,
        metagen: MetaGenConfig,
        metadata_fields: list[Any] | None,
    ) -> S5bMetagenStage:
        """
        Wire S5b from the metagen config + the collection's generated metadata fields.

        ``METAGEN_ENABLED`` is a deployment kill-switch: when false the stage is built with an
        empty target list (a no-op) regardless of config. ``METAGEN_MAX_BUDGET_USD`` caps the
        estimated per-document spend. The provider chain is built like the VLM chain (None when no
        provider configured → the stage no-ops). The ``field_types`` lookup resolves each target's
        declared type/enum from the metadata schema.

        Args:
            metagen (MetaGenConfig): The metagen config block.
            metadata_fields (list | None): The collection's metadata field specs.

        Returns:
            S5bMetagenStage: The wired metagen stage.
        """
        # The per-collection metagen config is the contract: a collection that declares a chain +
        # targets drives the stage on its own (mirrors every other per-collection provider config).
        # METAGEN_ENABLED is the DEFAULT-pipeline kill-switch only (build_default_pipeline), NOT a
        # gate on an explicitly-configured collection — gating targets here silently dropped a
        # collection's bindings while still building the chain, no-op'ing the stage.
        chain = ChainBuilderHelpers.build_metagen_chain(self._cfg, metagen.chain, metagen.gate)
        targets = list(metagen.targets)
        field_types = self._resolve_metagen_field_types(metadata_fields, metagen.targets)
        budget = float(getattr(self._cfg, "METAGEN_MAX_BUDGET_USD", 0.0))
        return S5bMetagenStage(
            llm_chain=chain,
            targets=targets,
            field_types=field_types,
            provider_cache=self._provider_cache,
            max_concurrency=metagen.max_concurrency,
            max_budget_usd=budget,
        )

    @staticmethod
    def _resolve_metagen_field_types(
        metadata_fields: list[Any] | None,
        targets: list[Any],
    ) -> dict[str, MetaFieldSpec]:
        """
        Build the type/enum lookup for the generated fields a metagen target references.

        Only fields authored as ``origin == "generated"`` AND referenced by a target are kept — the
        S5b stage must never write into a system/user field. Accepts both dict snapshots (the worker
        passes plain dicts decoupled from the ORM session) and ORM rows.

        Args:
            metadata_fields (list | None): The collection's metadata field specs.
            targets (list[MetaGenTarget]): The configured metagen targets.

        Returns:
            dict[str, MetaFieldSpec]: ``field_name → MetaFieldSpec`` for the eligible generated fields.
        """
        # 1. Nothing to resolve without fields or targets.
        if not metadata_fields or not targets:
            return {}

        def _attr(obj: Any, name: str, default: Any = None) -> Any:
            return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)

        target_names = {t.field for t in targets}
        field_types: dict[str, MetaFieldSpec] = {}
        # 2. Keep only generated fields that a target actually binds.
        for field in metadata_fields:
            name = _attr(field, "field_name")
            if not name or name not in target_names or _attr(field, "origin") != "generated":
                continue
            field_types[name] = MetaFieldSpec(
                field_name=name,
                field_type=_attr(field, "field_type", "string"),
                enum_values=_attr(field, "enum_values"),
                required=bool(_attr(field, "required", False)),
                origin="generated",
            )
        return field_types

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
