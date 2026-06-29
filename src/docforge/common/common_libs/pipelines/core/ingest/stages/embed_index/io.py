# ====== Code Summary ======
# IO contract for the embed_index stage: it consumes the contextualised/metagen'd chunks and the
# merged doc_meta from the metagen sibling, plus the activation collection id and the collection's
# metadata field defs from the pipeline run input. Its output is the single embed_index result
# (counts + per-batch embed chain traces) the orchestrator flushes onto the document lineage.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines import FromRunInput, FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .result import IngestStageEmbedIndexResult


class IngestStageEmbedIndexInput(NodeInput):
    """
    Input of the embed_index stage.

    Attributes:
        chunks (list[Chunk]): Contextualised chunks (embed_text + derived_meta populated) from metagen.
        doc_meta (dict): Merged document-level metadata (implicit < generated < user) from metagen.
        collection_id (str): Target collection — the stage runs only when a collection is set.
        metadata_fields (list | None): Collection metadata field defs (drive the vector plan + payload).
    """

    chunks: Annotated[list[Chunk], FromSibling(producer="metagen", field="chunks")]
    doc_meta: Annotated[dict[str, Any], FromSibling(producer="metagen", field="doc_meta")]
    collection_id: Annotated[str, FromRunInput()]
    metadata_fields: Annotated[list[Any] | None, FromRunInput(required=False)]


class IngestStageEmbedIndexOutput(NodeOutput):
    """
    Output of the embed_index stage — the assembled embed + index result.

    Attributes:
        embed_result (IngestStageEmbedIndexResult): Counts (embedded / upserted / persisted),
            target collection, per-field vector count, and the per-batch embed chain traces.
    """

    embed_result: IngestStageEmbedIndexResult


__all__ = ["IngestStageEmbedIndexInput", "IngestStageEmbedIndexOutput"]
