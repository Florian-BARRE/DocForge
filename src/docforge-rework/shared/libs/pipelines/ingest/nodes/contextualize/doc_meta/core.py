# ====== Code Summary ======
# The doc_meta contextualizer — prefixes every chunk with selected DOCUMENT metadata (title,
# author, date… from the source's declared metadata, validated at intake). Zero cost, local;
# anchors every chunk to its document identity for retrieval.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk, SourceDocument

# ====== Local Project Imports ======
from ..base import BaseContextualizerConfig, BaseContextualizerNode, ContextualizerConsumes


class ContextualizerDocMetaConfig(BaseContextualizerConfig):
    """Which declared metadata to render, and how."""

    fields: list[str] = Field(
        default_factory=list,
        description="Declared metadata fields to include (empty = all declared).",
    )
    line_template: str = Field(
        default="{name}: {value}", description="Rendered form of one field."
    )
    joiner: str = Field(default=" · ", description="Joiner between rendered fields.")


class DocMetaConsumes(ContextualizerConsumes):
    """The family face + the source document carrying the declared metadata."""

    source: SourceDocument = Field(
        description="The run's source document (its declared metadata is rendered)."
    )


@NodeRegistry.register("contextualize")
class ContextualizerDocMetaNode(BaseContextualizerNode):
    """Prefix each chunk with the document's declared metadata."""

    KIND = "doc_meta"
    NAME = "Document metadata"
    SUMMARY = "Prefix each chunk with selected document metadata (title, author, …)."
    HOW_IT_WORKS = (
        "Renders the chosen fields of the source's declared metadata (validated at intake) as "
        "one line, identical for every chunk of the document. Zero cost."
    )
    Config = ContextualizerDocMetaConfig
    UNIQUE_IN_GRAPH = True
    Consumes = DocMetaConsumes

    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """Render the document line (the same piece for every chunk)."""
        config: ContextualizerDocMetaConfig = self.config
        # 1. Select the declared fields (all of them when none are named).
        declared = data.source.declared_meta
        names = config.fields or list(declared)
        rendered = [
            config.line_template.format(name=name, value=declared[name])
            for name in names
            if name in declared and declared[name] not in (None, "")
        ]
        return config.joiner.join(rendered) if rendered else None


__all__ = ["ContextualizerDocMetaNode", "ContextualizerDocMetaConfig", "DocMetaConsumes"]
