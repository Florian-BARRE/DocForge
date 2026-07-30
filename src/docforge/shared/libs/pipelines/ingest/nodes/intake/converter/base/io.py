# ====== Code Summary ======
# The fixed I/O contract shared by EVERY converter: it consumes the admitted source plus what the
# bytes really are (the probe drives the routing), and produces the canonical PDF view. A converter
# is interchangeable behind these two faces, whatever engine performs the conversion.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models import PdfView, SourceDocument, SourceProbe


class ConverterConsumes(NodeInput):
    """Input of any converter — the source bytes and their detected nature."""

    source: SourceDocument = Field(description="The admitted document to convert.")
    probe: SourceProbe = Field(description="The detected format that routes the conversion.")


class ConverterProduces(NodeOutput):
    """Output of any converter — the canonical PDF view (content None when not convertible)."""

    pdf: PdfView = Field(
        description="The working PDF (content None when the format cannot be converted — "
        "downstream degrades)."
    )


__all__ = ["ConverterConsumes", "ConverterProduces"]
