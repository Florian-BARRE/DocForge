# ====== Code Summary ======
# MetagenStage — the native metagen (S5b) stage. Assembly-only: it DECLARES the forced ClassVars
# (matching the former s5b metagen adapter byte-for-byte) and wires its single MetagenStep around
# the injected metagen implementation. The stage PRODUCES doc_meta (assembled in the step) so the
# IO graph is closed for S6. CACHE_POLICY is IDEMPOTENT_WRITE, so it is never node-cached.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy, StageKey, StageSpec
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s5b_metagen.core import S5bMetagenStage

# ====== Local Project Imports ======
from .steps.metagen_step import MetagenStep


@register_stage
class MetagenStage(IngestStage):
    """
    Native metagen stage — generates per-chunk/per-doc metadata via its single MetagenStep.

    Declares the metagen contract (identity/ordering/IO/cache/error) and assembles its step around
    the metagen implementation; the run/track/fingerprint/describe machinery is inherited. The step
    also assembles ``doc_meta`` (the document-level merge) so the embed/index stage can consume it.
    """

    SPEC: ClassVar[StageSpec] = StageSpec(
        key=StageKey.METAGEN,
        name="Metagen",
        description=(
            "Generate LLM-derived metadata per chunk (derived_meta) and per document (doc_fields) "
            "via the metagen provider chain."
        ),
        after=(StageKey.CONTEXTUALIZE,),
        consumes=("chunks", "ir", "ingest_result", "doc_user_meta"),
        produces=("metagen_result", "chunks", "doc_fields", "doc_meta"),
        cache_policy=CachePolicy.IDEMPOTENT_WRITE,
        error_policy=ErrorPolicy.FAIL_DOC,
    )

    def __init__(self, inner: S5bMetagenStage) -> None:
        """
        Wire the stage around a metagen implementation and build its single step.

        Args:
            inner (S5bMetagenStage): The metagen implementation. Retained as ``self._inner`` so the
                assembler/parity checks can reach it.
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [MetagenStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The single native metagen step."""
        return self._steps


__all__ = ["MetagenStage"]
