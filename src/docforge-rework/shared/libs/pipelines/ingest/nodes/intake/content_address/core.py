# ====== Code Summary ======
# ContentAddressNode — the stage's terminal node: content-addresses the ORIGINAL bytes
# (sha256 — dedup and blob identity key on the same hash) and assembles the IntakeResult the parse
# stage consumes: hash + PDF view + routing facts.

# ====== Standard Library Imports ======
import hashlib

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import IntakeResult, PdfProbe, PdfView, SourceDocument


class ContentAddressConfig(NodeConfig):
    """No knobs — the hash algorithm is an identity contract, never a per-collection choice."""


class ContentAddressConsumes(NodeInput):
    """The admitted source, its PDF view, and the PDF routing facts."""

    source: SourceDocument = Field(description="The admitted document (its ORIGINAL bytes are hashed).")
    pdf: PdfView = Field(description="The working PDF carried into the stage output.")
    probe: PdfProbe = Field(description="The PDF facts carried into the stage output.")


class ContentAddressProduces(NodeOutput):
    """The stage output the parse stage consumes."""

    ingest: IntakeResult = Field(
        description="The intake stage output: source hash + working PDF + page count."
    )


@NodeRegistry.register("intake")
class ContentAddressNode(ActionNode):
    """Hash the original bytes and assemble the stage's IntakeResult."""

    KIND = "content_address"
    UNIQUE_IN_GRAPH = True
    NAME = "Content address"
    SUMMARY = "Hash the original bytes (sha256) and assemble the IntakeResult."
    HOW_IT_WORKS = (
        "The sha256 of the ORIGINAL bytes is the document's identity: the dedup key and the blob "
        "store key of the original are the same hash. The IntakeResult bundles it with the PDF "
        "view and the routing facts for the parse stage."
    )
    Config = ContentAddressConfig

    Consumes = ContentAddressConsumes
    Produces = ContentAddressProduces

    async def run(self, data: ContentAddressConsumes) -> ContentAddressProduces:
        """Hash and assemble."""
        # 1. Content-address the ORIGINAL bytes (not the PDF view — identity follows the upload).
        source_hash = hashlib.sha256(data.source.content).hexdigest()
        self.logger.debug(f"Content-addressed '{data.source.filename}' as {source_hash[:12]}…")

        # 2. Assemble the stage output.
        return ContentAddressProduces(
            ingest=IntakeResult(
                source_hash=source_hash,
                pdf_content=data.pdf.content,
                page_count=data.probe.page_count,
            )
        )


__all__ = ["ContentAddressNode", "ContentAddressConfig"]
