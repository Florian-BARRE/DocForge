# ====== Code Summary ======
# The document-scope metagen PREP node — builds ONE word-capped document view from the chunks' raw
# texts, resolves the GENERATED/DOCUMENT targets, and emits one GenerationRequest per call group with
# chunk_id=None. The downstream structgen ForEach turns each request into GeneratedValues; the
# document-apply node merges them into one GeneratedDocumentMeta. No targets or no chunks means an
# empty request list — the loop and apply no-op (nothing declared, nothing spent).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk, CollectionContract, FieldScope, GenerationRequest

# ====== Local Project Imports ======
from .base import BaseMetagenPrep
from .config import MetagenPrepConfig


class MetagenDocumentPrepConfig(MetagenPrepConfig):
    """Document-scope prep config (the shared prep knobs are everything it needs)."""


class MetagenDocumentPrepConsumes(NodeInput):
    """Input: the chunks (the document view is built from them) + the contract."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The chunks (the document view's text source)."
    )
    contract: CollectionContract = Field(
        description="The contract declaring the GENERATED document-scope fields to fill."
    )


class MetagenDocumentPrepProduces(NodeOutput):
    """Output: one GenerationRequest per call group over the document view (chunk_id=None)."""

    requests: list[GenerationRequest] = Field(
        default_factory=list,
        description="One structured-generation call per endpoint group, over the document view.",
    )


@NodeRegistry.register("metagen")
class MetagenDocumentPrepNode(BaseMetagenPrep):
    """Emit the DOCUMENT-scope generation requests declared by the contract, in one pass."""

    KIND = "document_prep"
    NAME = "Document metadata prep"
    SUMMARY = "Emit the structured-generation requests for the contract's document-scope fields."
    HOW_IT_WORKS = (
        "Resolves the GENERATED/DOCUMENT fields (contract declares, targets bind prompt + endpoint "
        "per field), builds the word-capped document view from the chunks' raw texts, and emits one "
        "GenerationRequest per call group (chunk_id=None) — no model call here. A bad target fails "
        "loudly before any spend."
    )
    Config = MetagenDocumentPrepConfig
    Consumes = MetagenDocumentPrepConsumes
    Produces = MetagenDocumentPrepProduces

    async def run(self, data: MetagenDocumentPrepConsumes) -> MetagenDocumentPrepProduces:
        """
        Emit the document-scope generation requests.

        Args:
            data (MetagenDocumentPrepConsumes): The chunks + the contract.

        Returns:
            MetagenDocumentPrepProduces: One request per call group over the document view.
        """
        config: MetagenDocumentPrepConfig = self.config
        # 1. What this node must fill — a bad target raises here, before any spend.
        targets = self._resolve_targets(data.contract, FieldScope.DOCUMENT)
        if not targets or not data.chunks:
            return MetagenDocumentPrepProduces(requests=[])

        # 2. One document view, then one request per call group (chunk_id=None).
        text = self._document_text([chunk.text for chunk in data.chunks], config.max_document_words)
        requests = self._build_requests(text, None, targets, "doc")
        self.logger.debug(f"Prepared {len(requests)} document-scope request(s)")
        return MetagenDocumentPrepProduces(requests=requests)


__all__ = [
    "MetagenDocumentPrepNode",
    "MetagenDocumentPrepConfig",
    "MetagenDocumentPrepConsumes",
    "MetagenDocumentPrepProduces",
]
