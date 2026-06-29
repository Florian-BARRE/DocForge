# ====== Code Summary ======
# IngestDocStage — the native ingest (S0) stage. Assembly-only: it DECLARES the forced ClassVars
# (matching the former s0 ingest adapter byte-for-byte) and wires its single IngestDocStep around
# the injected ingestion implementation. The class is named IngestDocStage (not IngestStage) so it
# does not collide with the ingest-family stage base ``IngestStage``.
#
# Parity contract (must equal the old s0 adapter): KEY="ingest", NODE_TYPE="s0", AFTER=(),
# CONSUMES=("file_bytes","filename","doc_id"), PRODUCES=("s0_result","source_hash"),
# CACHE_POLICY=NODE_CACHED, ON_ERROR=FAIL_DOC, NODE_VERSION="1.0", and fingerprint_params()=
# {"converter_name": ..., "converter_version": ...} — NODE_TYPE "s0" + the overridden
# fingerprint_params reproduce the legacy S0 node-cache key exactly.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage

# ====== Local Project Imports ======
from .steps.ingest_step import IngestDocStep


@register_stage
class IngestDocStage(IngestStage):
    """
    Native ingest stage — content-addresses + converts + uploads via its single IngestDocStep.

    Declares the ingest contract (identity/ordering/IO/cache/error) and assembles its step around
    the ingestion implementation; the run/track/fingerprint/describe machinery is inherited. Pinned
    to the legacy node id ``s0`` so its Merkle fingerprint + ``stage_run`` rows stay byte-identical
    to the legacy engine.
    """

    KEY: ClassVar[str] = "ingest"
    NAME: ClassVar[str] = "Ingest"
    DESCRIPTION: ClassVar[str] = (
        "Content-address the original, convert office formats to PDF, detect the OCR fork, "
        "and upload artifacts to the object store."
    )
    AFTER: ClassVar[tuple[str, ...]] = ()
    CONFIG: ClassVar[None] = None
    CONSUMES: ClassVar[tuple[str, ...]] = ("file_bytes", "filename", "doc_id")
    PRODUCES: ClassVar[tuple[str, ...]] = ("s0_result", "source_hash")
    CACHE_POLICY: ClassVar[CachePolicy] = CachePolicy.NODE_CACHED
    ON_ERROR: ClassVar[ErrorPolicy] = ErrorPolicy.FAIL_DOC
    # Legacy node id/type so the fingerprint hex + stage_run rows match the old engine exactly.
    NODE_TYPE: ClassVar[str] = "s0"

    def __init__(self, inner: S0IngestStage) -> None:
        """
        Wire the stage around an ingestion implementation and build its single step.

        Args:
            inner (S0IngestStage): The ingestion implementation. Retained as ``self._inner`` so the
                assembler/parity checks can reach the converter.
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [IngestDocStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The single native ingest step."""
        return self._steps

    def fingerprint_params(self) -> dict[str, object]:
        """
        Surface the legacy S0 node fingerprint params (converter name + version).

        Overrides the inherited step-aggregate so the dynamic engine reproduces the legacy S0
        node-cache key exactly (with ``NODE_TYPE="s0"`` and ``NODE_VERSION="1.0"``). Reads the
        ingestion stage's private converter, as the legacy ``S012ParamHelpers.s0_params`` does.

        Returns:
            dict[str, object]: ``{"converter_name": ..., "converter_version": ...}``.
        """
        converter = self._inner._converter
        return {
            "converter_name": getattr(converter, "name", "gotenberg"),
            "converter_version": getattr(converter, "version", "8"),
        }


__all__ = ["IngestDocStage"]
