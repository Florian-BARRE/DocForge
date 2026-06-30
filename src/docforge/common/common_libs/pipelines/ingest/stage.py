# ====== Code Summary ======
# The ingest stage — a GROUP wiring its three action nodes (content_address -> convert -> probe) with
# ``always`` transitions (a sequence). Its typed Output is ASSEMBLED from all three children (the
# multi-source data axis), giving downstream stages the document identity, the PDF view, and the probe
# hints. The stage holds no I/O itself — every side effect lives in its leaf nodes.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import (
    FromRunInput,
    GroupNode,
    NodeInput,
    NodeOutput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import IngestContentAddress, IngestConvert, IngestProbe


class IngestStageInput(NodeInput):
    """The ingest stage input — the raw original + filename (from the pipeline run input)."""

    original_bytes: Annotated[bytes, FromRunInput()]
    filename: Annotated[str, FromRunInput()]


class IngestStageOutput(NodeOutput):
    """The assembled ingest output consumed by the parse stage."""

    source_hash: str
    original_format: str
    original_key: str
    pdf_key: str | None
    converted: bool
    page_count: int | None
    needs_ocr: bool
    media_type: str
    # File-intrinsic metadata (lowest-precedence layer of the document's doc_meta).
    implicit_meta: dict


class IngestStage(GroupNode):
    """Ingest: content-address -> convert to PDF -> probe, assembled into the stage output."""

    Input = IngestStageInput
    Output = IngestStageOutput
    CACHED = True  # the whole stage is a Merkle node in the worker node-cache

    def __init__(self) -> None:
        """Wire the three ingest nodes as a sequence (``always`` edges)."""
        super().__init__(
            "ingest",
            [
                IngestContentAddress("content_address"),
                IngestConvert("convert"),
                IngestProbe("probe"),
            ],
            [Transition("content_address", "convert"), Transition("convert", "probe")],
        )

    def assemble(self, outputs: dict, terminal: NodeOutput) -> IngestStageOutput:
        """
        Assemble the stage output from all three nodes (identity + PDF view + probe hints).

        Args:
            outputs (dict): The three child outputs by id.
            terminal (NodeOutput): The terminal output (unused — the stage combines all three).

        Returns:
            IngestStageOutput: The combined ingest result.
        """
        ca, cv, pr = outputs["content_address"], outputs["convert"], outputs["probe"]
        return IngestStageOutput(
            source_hash=ca.source_hash,
            original_format=ca.original_format,
            original_key=ca.original_key,
            pdf_key=cv.pdf_key,
            converted=cv.converted,
            page_count=cv.page_count,
            needs_ocr=pr.needs_ocr,
            media_type=pr.media_type,
            implicit_meta=self._build_implicit_meta(ca, cv, pr),
        )

    @staticmethod
    def _build_implicit_meta(ca: NodeOutput, cv: NodeOutput, pr: NodeOutput) -> dict:
        """
        Build the file-intrinsic implicit metadata (the lowest-precedence doc_meta layer).

        Args:
            ca (NodeOutput): The content-address output (filename / format / size / hash).
            cv (NodeOutput): The convert output (PDF page count).
            pr (NodeOutput): The probe output (the OCR hint).

        Returns:
            dict: File-intrinsic metadata keyed by spec field names.
        """
        return {
            "filename": ca.filename,
            "extension": ca.original_format,
            "file_size": ca.file_size,
            "source_hash": ca.source_hash,
            "page_count": cv.page_count,
            "has_scanned_pages": pr.needs_ocr,
        }


__all__ = ["IngestStage", "IngestStageInput", "IngestStageOutput"]
