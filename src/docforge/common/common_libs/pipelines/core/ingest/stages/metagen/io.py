# ====== Code Summary ======
# IO contract for the metagen stage (StageKey.METAGEN). It reads the contextualized chunks (from the
# contextualize stage), the enriched IR (from the enrich stage), the file-intrinsic implicit_meta
# (from the ingest stage), and the caller-supplied doc_user_meta (from the run input). It produces the
# same chunks (with chunk-scope ``derived_meta`` filled), the document-scope ``doc_fields``, the merged
# ``doc_meta`` (implicit < generated < user), and the ``metagen_result`` record. ``doc_meta`` closes the
# IO graph so the embed/index stage can consume the document-level metadata.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, DocumentIR
from common_libs.pipelines import FromRunInput, FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .result import IngestStageMetagenResult


class IngestStageMetagenInput(NodeInput):
    """
    Input of the metagen stage.

    Attributes:
        chunks (list[Chunk]): Contextualized chunks (from the contextualize stage).
        ir (DocumentIR): The enriched IR (from the enrich stage) — document-scope digest source.
        implicit_meta (dict): File-intrinsic metadata (from the ingest stage), lowest precedence.
        doc_user_meta (dict | None): Caller-supplied document metadata (from the run input), highest
            precedence; None when the caller supplied none.
    """

    chunks: Annotated[list[Chunk], FromSibling(producer="contextualize", field="chunks")]
    ir: Annotated[DocumentIR, FromSibling(producer="enrich", field="ir")]
    implicit_meta: Annotated[dict, FromSibling(producer="ingest", field="implicit_meta")]
    doc_user_meta: Annotated[dict | None, FromRunInput(required=False)]


class IngestStageMetagenOutput(NodeOutput):
    """
    Output of the metagen stage — the assembled result of its four steps.

    Attributes:
        chunks (list[Chunk]): The same chunks, with chunk-scope generated values written into each
            ``chunk.derived_meta``.
        doc_fields (dict): Document-scope generated values ``{field_name: value}``.
        doc_meta (dict): The merged document-level metadata (implicit < generated < user) consumed by
            the embed/index stage.
        metagen_result (IngestStageMetagenResult): Counts, estimated cost, and chain traces.
    """

    chunks: list[Chunk]
    doc_fields: dict
    doc_meta: dict
    metagen_result: IngestStageMetagenResult


__all__ = ["IngestStageMetagenInput", "IngestStageMetagenOutput"]
