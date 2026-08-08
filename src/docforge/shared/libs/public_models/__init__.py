# ---------------------- Artefact base ---------------------- #
from .base import Artifact, TimeoutConfig, TimeoutRetryConfig

# ---------------------- IR (canonical parsed document) ---------------------- #
from .ir import (
    FIGURE_ROUTING,
    TOC_TITLES,
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    FigureRouting,
    Provenance,
    TableData,
    figure_prompt_lines,
    first_heading,
    is_toc_title,
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
from .chunk_role import ChunkRole, role_default_enabled

# ---------------------- Metagen (generated metadata) ---------------------- #
from .metagen import GeneratedDocumentMeta

# ---------------------- OpenAI-compatible endpoint (shared config vocabulary) ---------------------- #
from .endpoint import OpenAICompatConfig

# ---------------------- Structured generation (structgen capability I/O) ---------------------- #
from .structgen import GeneratedValues, GenerationField, GenerationRequest

# ---------------------- Embeddings (vectors, chunk-linked) ---------------------- #
from .embed import ChunkEmbeddings, ChunkVectors, SparseVector

# ---------------------- Run delivery (the pipeline's output contract) ---------------------- #
from .bundle import RunBundle

# ---------------------- LLM ---------------------- #
from .llm import Completion, Prompt

# ------------------- Public API ------------------- #
__all__ = [
    "Artifact",
    "TimeoutConfig",
    "TimeoutRetryConfig",
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
    "TOC_TITLES",
    "is_toc_title",
    "first_heading",
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
    "ChunkRole",
    "role_default_enabled",
    "GeneratedDocumentMeta",
    "OpenAICompatConfig",
    "GenerationField",
    "GenerationRequest",
    "GeneratedValues",
    "SparseVector",
    "ChunkVectors",
    "ChunkEmbeddings",
    "RunBundle",
    "Prompt",
    "Completion",
]
