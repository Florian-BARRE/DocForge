# ====== Code Summary ======
# ParsingStage — the native parse stage, decomposed into THREE real steps: ParseStep (drive the
# parser chain → canonical IR + lineage) → FigureRenderStep (crop + upload + patch figure crops) →
# MarkdownStep (serialise + upload markdown, assemble the ParseResult). Assembly-only: it DECLARES
# the forced SPEC and wires the three steps around its resource bundle (parser chain + object store);
# the run/track/describe machinery is inherited.
#
# Node-cache parity: CACHE_POLICY=NODE_CACHED + key=StageKey.PARSE + code_version="1.0", and
# fingerprint_params() returns the parser chain signature ({"parse_chain": <signature>}) so the
# Merkle node-cache key matches the legacy S1 exactly (the inherited per-step aggregate would
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
from .steps.figure_render_step import FigureRenderStep
from .steps.markdown_step import MarkdownStep
from .steps.parse_step import ParseStep

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.chain import Chain
    from common_libs.storage.s3.client import S3Client


@dataclass(frozen=True)
class ParseResources:
    """
    The parse stage's dependency bundle — the bricks its steps execute against.

    Bundled into a single object so the assembler can wire the stage with the uniform
    ``stage_cls(inner)`` call while the steps each receive only the handle they need.

    Attributes:
        parse_chain (Chain): Ordered parser escalation chain (docling, …) the ParseStep drives.
        s3 (S3Client): SeaweedFS S3-compatible object store client (figure crops + markdown).
    """

    parse_chain: "Chain[Any, Any]"
    s3: "S3Client"


@register_stage
class ParsingStage(IngestStage):
    """
    Native parse stage — parses, renders figures, and serialises markdown in three real steps.

    Declares the parse contract (identity/ordering/IO/cache/error) and assembles its three steps
    around the injected resource bundle; the run/track/fingerprint/describe machinery is inherited.
    Pinned to ``StageKey.PARSE`` + ``code_version="1.0"`` so its Merkle fingerprint + ``stage_run``
    rows stay byte-identical to the legacy engine.
    """

    SPEC: ClassVar[StageSpec] = StageSpec(
        key=StageKey.PARSE,
        name="Parse",
        description=(
            "Parse the PDF into the canonical IR via the parser chain, render figure crops, and "
            "serialise the markdown view."
        ),
        after=(StageKey.INGEST,),
        consumes=("ingest_result",),
        produces=("parse_result", "ir"),
        cache_policy=CachePolicy.NODE_CACHED,
        error_policy=ErrorPolicy.FAIL_DOC,
    )

    def __init__(self, resources: ParseResources) -> None:
        """
        Wire the stage around its resource bundle and build its three steps.

        Args:
            resources (ParseResources): Parser chain + object store the steps execute against.
                Retained as ``self._resources`` so the assembler/parity checks + the node
                fingerprint can reach the parser chain signature.
        """
        IngestStage.__init__(self)
        self._resources = resources
        self._steps: list[AbstractStep] = [
            ParseStep(resources.parse_chain),
            FigureRenderStep(resources.s3),
            MarkdownStep(resources.s3),
        ]

    @property
    def steps(self) -> list[AbstractStep]:
        """The three native parse steps: parse → figure-render → markdown."""
        return self._steps

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the parser chain signature as the node fingerprint params.

        Overrides the inherited per-step aggregate so the dynamic engine reproduces the legacy S1
        node-cache key exactly (with ``key=StageKey.PARSE`` and ``code_version="1.0"``). Any change
        to a parser provider/version invalidates the parse node.

        Returns:
            dict[str, Any]: ``{"parse_chain": <chain signature>}``.
        """
        return {"parse_chain": self._resources.parse_chain.signature()}


__all__ = ["ParsingStage", "ParseResources"]
