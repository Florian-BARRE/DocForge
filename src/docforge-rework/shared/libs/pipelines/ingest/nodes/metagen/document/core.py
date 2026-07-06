# ====== Code Summary ======
# The document-scope metagen node — fills every GENERATED/DOCUMENT field of the contract in one
# pass: the document view is built from the chunks' raw texts (word-capped), the targets bind
# prompt + LLM per field, the field types force the output shape, values are strictly coerced.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk, CollectionContract, FieldScope, GeneratedDocumentMeta

# ====== Local Project Imports ======
from ..base import BaseMetagenConfig, BaseMetagenNode


class MetagenDocumentConfig(BaseMetagenConfig):
    """Document-scope metagen config (the shared knobs are everything it needs)."""


class MetagenDocumentConsumes(NodeInput):
    """Input: the chunks (the document view is built from them) + the contract."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The chunks (the generation text source).",
    )
    contract: CollectionContract = Field(
        description="The contract declaring the GENERATED fields to fill."
    )


class MetagenDocumentProduces(NodeOutput):
    """Output: the document-scope generated values."""

    meta: GeneratedDocumentMeta = Field(
        description="The document-scope generated values, coerced to their contract types."
    )


@NodeRegistry.register("metagen")
class MetagenDocumentNode(BaseMetagenNode):
    """Generate the DOCUMENT-scope metadata declared by the contract."""

    KIND = "document"
    NAME = "Document metadata generation"
    SUMMARY = "Fill the contract's GENERATED document-scope fields from the document text."
    HOW_IT_WORKS = (
        "Resolves the GENERATED/DOCUMENT fields (contract declares, targets bind prompt + LLM "
        "per field), builds the document view from the chunks' raw texts, and runs the "
        "structured-output calls (grouped per endpoint or per field). Values are coerced to "
        "their contract type; unusable ones are dropped, never stored wrong."
    )
    Config = MetagenDocumentConfig
    Consumes = MetagenDocumentConsumes
    Produces = MetagenDocumentProduces

    async def run(self, data: MetagenDocumentConsumes) -> MetagenDocumentProduces:
        """
        Generate the document-scope values.

        Args:
            data (MetagenDocumentConsumes): The chunks + the contract.

        Returns:
            MetagenDocumentProduces: The coerced document-scope values.
        """
        config: MetagenDocumentConfig = self.config
        # 1. What this node must fill — nothing declared means nothing spent.
        targets = self._resolve_targets(data.contract, FieldScope.DOCUMENT)
        if not targets or not data.chunks:
            return MetagenDocumentProduces(meta=GeneratedDocumentMeta())

        # 2. One document view, then the grouped structured calls.
        text = self._document_text(
            [chunk.text for chunk in data.chunks], config.max_document_words
        )
        values = await self._generate_values(text, targets)
        self.logger.info(f"Generated {len(values)}/{len(targets)} document-scope field(s)")
        return MetagenDocumentProduces(meta=GeneratedDocumentMeta(values=values))


__all__ = ["MetagenDocumentNode", "MetagenDocumentConfig", "MetagenDocumentConsumes", "MetagenDocumentProduces"]
