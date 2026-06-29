# ====== Code Summary ======
# IngestStageIngest — the first stage of the ingest pipeline (StageKey.INGEST). It assembles its
# three steps (content-address -> convert -> probe; the engine derives that order from their input
# bindings) and aggregates their outputs into the single IngestStageIngestOutput consumed downstream.
# NODE_CACHED: the whole stage is a Merkle node in the cache.

# ====== Internal Project Imports ======
from common_libs2.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageIngestContext
from .errors import IngestStageIngestError
from .io import IngestStageIngestInput, IngestStageIngestOutput
from .steps import (
    IngestStageIngestStepContentAddress,
    IngestStageIngestStepConvert,
    IngestStageIngestStepProbe,
)


class IngestStageIngest(IngestStageBase):
    """
    Ingest stage — content-address, derive the PDF view, and probe the OCR fork.

    Declares its three steps; the engine orders + runs them and the stage aggregates their outputs.
    """

    SPEC = StageSpec(
        key=StageKey.INGEST,
        name="Ingest",
        description="Content-address + convert + probe the original document.",
        cache_policy=CachePolicy.NODE_CACHED,
    )
    Input = IngestStageIngestInput
    Output = IngestStageIngestOutput
    Context = IngestStageIngestContext
    Error = IngestStageIngestError

    def __init__(self) -> None:
        """Build the three ingest steps in declaration order (the engine topo-orders them)."""
        super().__init__()
        self._steps = [
            IngestStageIngestStepContentAddress(),
            IngestStageIngestStepConvert(),
            IngestStageIngestStepProbe(),
        ]

    @property
    def children(self) -> list:
        """The ingest steps (content-address -> convert -> probe)."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageIngestOutput:
        """
        Combine the three step outputs into the stage output.

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageIngestOutput: The assembled ingest result.
        """
        # 1. Pull each step's typed output by its step key.
        addressed = child_outputs["content_address"]
        converted = child_outputs["convert"]
        probed = child_outputs["probe"]

        # 2. Assemble the single downstream-facing artefact.
        return IngestStageIngestOutput(
            doc_id=addressed.doc_id,
            source_hash=addressed.source_hash,
            original_format=addressed.original_format,
            original_key=addressed.original_key,
            pdf_key=converted.pdf_key,
            converted=converted.converted,
            page_count=converted.page_count,
            needs_ocr=probed.needs_ocr,
            media_type=probed.media_type,
        )


__all__ = ["IngestStageIngest"]
