# ====== Code Summary ======
# IngestDocStage — the native ingest stage, decomposed into THREE real steps: ContentAddressStep
# (SHA-256 + upload original) → ConvertStep (derive PDF + upload) → ProbeStep (OCR fork + assemble
# the IngestResult). Assembly-only: it DECLARES the forced SPEC and wires the three steps around its
# resource bundle (object store + converter brick); the run/track/describe machinery is inherited.
# The class is named IngestDocStage (not IngestStage) so it does not collide with the ingest-family
# stage base ``IngestStage``.
#
# Node-cache parity: CACHE_POLICY=NODE_CACHED + key=StageKey.INGEST + code_version="1.0", and
# fingerprint_params() returns the converter identity ({"converter_name","converter_version"}) so
# the Merkle node-cache key matches the legacy S0 exactly (the inherited per-step aggregate would
# otherwise change the key).

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
from .steps.content_address_step import ContentAddressStep
from .steps.convert_step import ConvertStep
from .steps.probe_step import ProbeStep

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.providers.converter import GotenbergConverter
    from common_libs.storage.s3.client import S3Client


@dataclass(frozen=True)
class IngestResources:
    """
    The ingest stage's dependency bundle — the bricks its steps execute against.

    Bundled into a single object so the assembler can wire the stage with the uniform
    ``stage_cls(inner)`` call while the steps each receive only the handle they need.

    Attributes:
        s3 (S3Client): SeaweedFS S3-compatible object store client.
        converter (GotenbergConverter): Gotenberg client for office → PDF conversion.
    """

    s3: "S3Client"
    converter: "GotenbergConverter"


@register_stage
class IngestDocStage(IngestStage):
    """
    Native ingest stage — content-addresses, converts, and probes in three real steps.

    Declares the ingest contract (identity/ordering/IO/cache/error) and assembles its three steps
    around the injected resource bundle; the run/track/fingerprint/describe machinery is inherited.
    Pinned to ``StageKey.INGEST`` + ``code_version="1.0"`` so its Merkle fingerprint + ``stage_run``
    rows stay byte-identical to the legacy engine.
    """

    SPEC: ClassVar[StageSpec] = StageSpec(
        key=StageKey.INGEST,
        name="Ingest",
        description=(
            "Content-address the original, convert office formats to PDF, detect the OCR fork, "
            "and upload artifacts to the object store."
        ),
        after=(),
        consumes=("original_bytes", "filename", "doc_id"),
        produces=("ingest_result", "source_hash"),
        cache_policy=CachePolicy.NODE_CACHED,
        error_policy=ErrorPolicy.FAIL_DOC,
    )

    def __init__(self, resources: IngestResources) -> None:
        """
        Wire the stage around its resource bundle and build its three steps.

        Args:
            resources (IngestResources): Object store + converter brick the steps execute against.
                Retained as ``self._resources`` so the assembler/parity checks + the node
                fingerprint can reach the converter identity.
        """
        IngestStage.__init__(self)
        self._resources = resources
        self._steps: list[AbstractStep] = [
            ContentAddressStep(resources.s3),
            ConvertStep(resources.s3, resources.converter),
            ProbeStep(),
        ]

    @property
    def steps(self) -> list[AbstractStep]:
        """The three native ingest steps: content-address → convert → probe."""
        return self._steps

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the converter identity (name + version) as the node fingerprint params.

        Overrides the inherited per-step aggregate so the dynamic engine reproduces the legacy S0
        node-cache key exactly (with ``key=StageKey.INGEST`` and ``code_version="1.0"``).

        Returns:
            dict[str, Any]: ``{"converter_name": ..., "converter_version": ...}``.
        """
        converter = self._resources.converter
        return {
            "converter_name": getattr(converter, "name", "gotenberg"),
            "converter_version": getattr(converter, "version", "8"),
        }


__all__ = ["IngestDocStage", "IngestResources"]
