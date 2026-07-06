# ====== Code Summary ======
# FormatProbeNode — establishes what the uploaded bytes REALLY are (content sniffing, never the
# extension) so the converter routes on truth and a spoofed extension cannot smuggle content past
# the admission gate. Emits the SourceProbe the rest of the stage keys on.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SourceDocument, SourceProbe

# ====== Local Project Imports ======
from .helpers import FormatProbeHelpers


class FormatProbeConfig(NodeConfig):
    """The probe has no knobs yet — detection rules are deterministic."""


class FormatProbeConsumes(NodeInput):
    """The admitted source to sniff."""

    source: SourceDocument = Field(description="The uploaded document to sniff (raw bytes).")


class FormatProbeProduces(NodeOutput):
    """What the bytes actually are."""

    probe: SourceProbe = Field(description="The REAL detected format, mime type and size.")


@NodeRegistry.register("intake")
class FormatProbeNode(ActionNode):
    """Detect the real format and MIME type of the uploaded bytes."""

    KIND = "format_probe"
    UNIQUE_IN_GRAPH = True
    NAME = "Content probe"
    SUMMARY = "Detect what the uploaded bytes really are (format + MIME), from content."
    HOW_IT_WORKS = (
        "Byte signatures (PDF/PNG/JPEG), zip-container inspection for office formats "
        "(docx/xlsx/pptx/odt), an HTML sniff, then a UTF-8 text fallback."
    )
    Config = FormatProbeConfig

    Consumes = FormatProbeConsumes
    Produces = FormatProbeProduces

    async def run(self, data: FormatProbeConsumes) -> FormatProbeProduces:
        """Sniff the content and report the detected format, MIME and size."""
        # 1. Detect from content (the filename only disambiguates markdown from plain text).
        detected_format, mime_type = FormatProbeHelpers.detect(data.source.content, data.source.filename)
        self.logger.debug(f"Probed '{data.source.filename}' as {detected_format} ({mime_type})")

        # 2. Report.
        return FormatProbeProduces(
            probe=SourceProbe(
                format=detected_format, mime_type=mime_type, file_size=len(data.source.content)
            )
        )


__all__ = ["FormatProbeNode", "FormatProbeConfig"]
