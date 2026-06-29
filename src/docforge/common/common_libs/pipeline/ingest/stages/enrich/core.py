# ====== Code Summary ======
# EnrichStage — the native enrich (S2) stage, decomposed into REAL per-capability steps:
# ClassifyStep (always) -> OcrStep (iff an OCR chain) -> VlmStep (iff a VLM chain) -> ChartStep (iff
# chart_to_data). Where the legacy S2EnrichStage routed each figure end-to-end, the native stage runs
# ONE capability over ALL figures per step (each step is its own trace entry + independently
# parametrizable), threading the per-figure routing decision + intermediate artefacts through an
# EnrichScratch in ctx.aux. The classify step records the routing decision once; the later passes act
# on exactly the figures it marked, so the enriched IR + counters are behaviour-equivalent to the
# legacy per-figure path (the provider-call cache keys are content-based, hence order-independent).
#
# Assembly-only: it DECLARES the forced SPEC (matching the former s2 adapter byte-for-byte) and wires
# its steps around an EnrichResources bundle. fingerprint_params surfaces the legacy S2 params
# (classifier/OCR/VLM signatures + chart_to_data) and key=StageKey.ENRICH pins the legacy node id, so
# the node-cache key is byte-identical to the old engine. describe() is inherited (the real steps
# self-describe), so the self-describing API surfaces the genuine per-capability structure.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy, StageKey, StageSpec
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage

# ====== Local Project Imports ======
from .steps.chart_step import ChartStep
from .steps.classify_step import ClassifyStep
from .steps.ocr_step import OcrStep
from .steps.vlm_step import VlmStep

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.chain import Chain
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache
    from common_libs.storage.s3.client import S3Client


@dataclass(frozen=True)
class EnrichResources:
    """
    The enrich stage's dependency bundle — the chains + infra its capability steps execute against.

    Bundled into a single object so the assembler can wire the stage with the uniform
    ``stage_cls(inner)`` call while each step receives only the chain/handle it needs. Exposes
    ``params_for_fingerprint`` so the stage (and the shared ``_build_s2`` parity check) reproduces the
    legacy S2 node-cache key exactly.

    Attributes:
        classifier_chain (Chain[Any, Any]): Ordered figure classifier chain (always non-empty).
        ocr_chain (Chain[Any, Any] | None): Ordered OCR chain; None disables OCR routing entirely.
        vlm_chain (Chain[Any, Any] | None): Ordered VLM chain; None disables VLM routing entirely.
        s3 (S3Client): SeaweedFS client for figure crop downloads.
        provider_cache (ProviderCallCache): Cross-document provider-call cache.
        chart_to_data (bool): When True, CHART figures additionally request structured chart-to-data
            extraction. Mirrors ``EnrichConfig.chart_to_data``.
    """

    classifier_chain: "Chain[Any, Any]"
    ocr_chain: "Chain[Any, Any] | None"
    vlm_chain: "Chain[Any, Any] | None"
    s3: "S3Client"
    provider_cache: "ProviderCallCache"
    chart_to_data: bool = False

    def params_for_fingerprint(self) -> dict[str, Any]:
        """
        Surface the legacy S2 fingerprint params (verbatim from the deleted S2EnrichStage).

        Any change to the classifier / OCR / VLM chains' signatures — or to ``chart_to_data`` (it
        changes the VLM schema + the data_table output) — invalidates the enrich node cache for all
        documents (and the downstream chunks/embeddings).

        Returns:
            dict[str, Any]: Fingerprint dict for the stage engine's Merkle-DAG.
        """
        return {
            "classifier_chain": self.classifier_chain.signature(),
            "ocr_chain": self.ocr_chain.signature() if self.ocr_chain else "none",
            "vlm_chain": self.vlm_chain.signature() if self.vlm_chain else "none",
            "chart_to_data": self.chart_to_data,
        }


@register_stage
class EnrichStage(IngestStage):
    """
    Native enrich stage — classifies + routes figures via REAL per-capability steps.

    Declares the enrich contract (identity/ordering/IO/cache/error), pins the legacy ``enrich`` node
    id, and assembles its steps around the injected :class:`EnrichResources`. The optional OCR / VLM /
    chart steps are built only when their chain / flag is present, so ``describe()`` (inherited)
    surfaces exactly the capabilities that can run.
    """

    SPEC: ClassVar[StageSpec] = StageSpec(
        key=StageKey.ENRICH,
        name="Enrich",
        description=(
            "Classify each figure and route it through OCR / VLM / chart-to-data passes, enriching "
            "the IR in place."
        ),
        after=(StageKey.PARSE,),
        consumes=("parse_result", "ir"),
        produces=("enrich_result", "ir"),
        cache_policy=CachePolicy.NODE_CACHED,
        error_policy=ErrorPolicy.FAIL_DOC,
    )

    def __init__(self, resources: EnrichResources) -> None:
        """
        Wire the stage around its resource bundle and build its per-capability steps.

        The classify step is always built; OCR / VLM steps are built only when their chain is wired;
        the chart step only when ``chart_to_data`` is on. Retains ``self._resources`` so the assembler
        / parity checks + the node fingerprint can reach the chains.

        Args:
            resources (EnrichResources): The chains + object store + provider cache + chart flag.
        """
        IngestStage.__init__(self)
        self._resources = resources
        steps: list[AbstractStep] = [
            ClassifyStep(
                classifier_chain=resources.classifier_chain,
                s3=resources.s3,
                provider_cache=resources.provider_cache,
                ocr_enabled=resources.ocr_chain is not None,
                vlm_enabled=resources.vlm_chain is not None,
                chart_to_data=resources.chart_to_data,
            ),
        ]
        if resources.ocr_chain is not None:
            steps.append(OcrStep(resources.ocr_chain, resources.provider_cache))
        if resources.vlm_chain is not None:
            steps.append(VlmStep(resources.vlm_chain, resources.provider_cache))
        if resources.chart_to_data:
            steps.append(ChartStep())
        self._steps = steps

    @property
    def steps(self) -> list[AbstractStep]:
        """The per-capability enrich steps: classify -> (ocr) -> (vlm) -> (chart)."""
        return self._steps

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the legacy S2 node fingerprint params (classifier/OCR/VLM signatures + chart flag).

        Overrides the inherited step-aggregate so the dynamic engine reproduces the legacy S2
        node-cache key exactly (with ``key=StageKey.ENRICH`` and ``code_version="1.0"``).

        Returns:
            dict[str, Any]: The legacy S2 fingerprint parameter dict.
        """
        return self._resources.params_for_fingerprint()


__all__ = ["EnrichStage", "EnrichResources"]
