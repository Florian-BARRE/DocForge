# ====== Code Summary ======
# IO contract for the convert step: it consumes the content-address step's output (source hash,
# original format, original key) via FromSibling and the raw bytes from the parent stage, and
# produces the PDF location + whether a conversion actually happened.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput


class IngestStageIngestStepConvertInput(NodeInput):
    """
    Input of the convert step.

    Attributes:
        source_hash (str): Content address (from the content-address step).
        original_format (str): Original file format (from the content-address step).
        original_key (str): Object-store key of the original (from the content-address step).
        original_bytes (bytes): Raw original bytes (from the parent stage input).
    """

    source_hash: Annotated[str, FromSibling(producer="content_address", field="source_hash")]
    original_format: Annotated[
        str, FromSibling(producer="content_address", field="original_format")
    ]
    original_key: Annotated[str, FromSibling(producer="content_address", field="original_key")]
    filename: Annotated[str, FromParent()]
    original_bytes: Annotated[bytes, FromParent()]


class IngestStageIngestStepConvertOutput(NodeOutput):
    """
    Output of the convert step.

    Attributes:
        pdf_key (str | None): Object-store key of the PDF view, or None when there is no PDF.
        converted (bool): True when an actual office/HTML -> PDF conversion was performed.
        page_count (int | None): Page count of the converted PDF, or None when not converted.
    """

    pdf_key: str | None
    converted: bool
    page_count: int | None = None


__all__ = [
    "IngestStageIngestStepConvertInput",
    "IngestStageIngestStepConvertOutput",
]
