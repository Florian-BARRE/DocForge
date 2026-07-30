# ====== Code Summary ======
# The document-scope metagen APPLY node — the back half of the externalised document metagen. It takes
# the GeneratedValues a structgen ForEach produced (all document-scope, chunk_id=None, one per call
# group) and merges every values dict into ONE GeneratedDocumentMeta, exactly as the old monolithic
# document node merged its per-endpoint groups into a single result. A skip-terminal's empty result
# simply contributes nothing.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import GeneratedDocumentMeta, GeneratedValues


class MetagenDocumentApplyConfig(NodeConfig):
    """No knobs — merging generated values into one document meta is a pure structural join."""


class MetagenDocumentApplyConsumes(NodeInput):
    """Input: the document-scope generated values the chain produced (all chunk_id=None)."""

    values: list[GeneratedValues] = Field(
        default_factory=list,
        description="The document-scope generated values (one per call group) the loop produced.",
    )


class MetagenDocumentApplyProduces(NodeOutput):
    """Output: the merged document-scope generated metadata."""

    meta: GeneratedDocumentMeta = Field(
        description="The document-scope generated values, merged into one, coerced to contract types."
    )


@NodeRegistry.register("metagen")
class MetagenDocumentApplyNode(ActionNode):
    """Merge the structgen loop's document-scope values into one GeneratedDocumentMeta."""

    KIND = "document_apply"
    SELECTABLE = False  # internal wiring — the stage builder emits it, not a user-picked method
    NAME = "Document metadata apply"
    SUMMARY = "Merge the generated document-scope values into one document metadata artefact."
    HOW_IT_WORKS = (
        "Merges every produced GeneratedValues dict into a single GeneratedDocumentMeta (later groups "
        "win on a key collision, as combined/per-field groups never overlap fields). An empty result "
        "contributes nothing."
    )
    Config = MetagenDocumentApplyConfig
    Consumes = MetagenDocumentApplyConsumes
    Produces = MetagenDocumentApplyProduces

    async def run(self, data: MetagenDocumentApplyConsumes) -> MetagenDocumentApplyProduces:
        """
        Merge the generated values into one document metadata artefact.

        Args:
            data (MetagenDocumentApplyConsumes): The document-scope generated values.

        Returns:
            MetagenDocumentApplyProduces: The merged document metadata.
        """
        # 1. Merge every group's values into one dict (groups partition the fields — no real overlap).
        merged: dict[str, Any] = {}
        for produced in data.values:
            merged.update(produced.values)
        self.logger.debug(
            f"Merged {len(merged)} document-scope field(s) from {len(data.values)} group(s)"
        )
        return MetagenDocumentApplyProduces(meta=GeneratedDocumentMeta(values=merged))


__all__ = [
    "MetagenDocumentApplyNode",
    "MetagenDocumentApplyConfig",
    "MetagenDocumentApplyConsumes",
    "MetagenDocumentApplyProduces",
]
