# ---------------------- Artefact base ---------------------- #
from .base import Artifact

# ---------------------- IR (canonical parsed document) ---------------------- #
from .ir import (
    FIGURE_ROUTING,
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    FigureRouting,
    Provenance,
    TableData,
    figure_prompt_lines,
)

# ---------------------- Collection contract vocabulary ---------------------- #
from .contract import (
    CollectionContract,
    FieldOrigin,
    FieldScope,
    FieldType,
    MetadataFieldSpec,
    UnknownFieldPolicy,
)

# ---------------------- Run inputs ---------------------- #
from .source import SourceDocument

# ---------------------- Intake (stage 1 artefacts) ---------------------- #
from .intake import IntakeResult, PdfProbe, PdfView, SourceProbe

# ---------------------- Page renders (parse output, UI + blobs) ---------------------- #
from .render import PageRender, PageRenders

# ---------------------- Enrich (per-item flow) ---------------------- #
from .enrich import EnrichmentEntry, FigureItem

# ---------------------- Chunks (retrieval units) ---------------------- #
from .chunk import Chunk

# ---------------------- Metagen (generated metadata) ---------------------- #
from .metagen import GeneratedDocumentMeta

# ---------------------- Embeddings (vectors, chunk-linked) ---------------------- #
from .embed import ChunkEmbeddings, ChunkVectors, SparseVector

# ---------------------- Run delivery (the pipeline's output contract) ---------------------- #
from .bundle import RunBundle

# ---------------------- LLM ---------------------- #
from .llm import Completion, Prompt

# ------------------- Public API ------------------- #
__all__ = [
    "Artifact",
    "BlockType",
    "FigureKind",
    "FigureRouting",
    "FIGURE_ROUTING",
    "figure_prompt_lines",
    "Provenance",
    "TableData",
    "FigureEnrichment",
    "Block",
    "DocumentIR",
    "FieldType",
    "FieldOrigin",
    "FieldScope",
    "UnknownFieldPolicy",
    "MetadataFieldSpec",
    "CollectionContract",
    "SourceDocument",
    "SourceProbe",
    "PdfView",
    "PdfProbe",
    "IntakeResult",
    "PageRender",
    "PageRenders",
    "FigureItem",
    "EnrichmentEntry",
    "Chunk",
    "GeneratedDocumentMeta",
    "SparseVector",
    "ChunkVectors",
    "ChunkEmbeddings",
    "RunBundle",
    "Prompt",
    "Completion",
]
