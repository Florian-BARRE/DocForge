# ====== Code Summary ======
# The ingest pipeline's IO contract. IngestInput is the RUN input the caller constructs and passes in
# the RunContext — it is the source of every ``FromRunInput`` binding in the stages, so its fields are
# plain (it is provided directly, not resolved). The pipeline's output is the ingest stage's output
# (the only stage in this end-to-end slice).

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeInput

# ====== Local Project Imports ======
from .stages.ingest import IngestStageIngestOutput

# The pipeline output IS the ingest stage output (single-stage slice). Re-exported under a pipeline
# name so callers depend on the pipeline contract, not the stage's.
IngestOutput = IngestStageIngestOutput


class IngestInput(NodeInput):
    """
    Run input for the ingest pipeline — constructed by the caller, passed in the RunContext.

    Attributes:
        original_bytes (bytes): The raw original file bytes.
        filename (str): The original filename.
        doc_id (str | None): A pre-assigned document id, or None to mint a fresh one.
        collection_id (str | None): Target collection (drives embed/index; None = no indexing).
        metadata_fields (list | None): The collection's metadata field specs (embed/index).
        doc_user_meta (dict | None): Caller-supplied per-document business metadata (metagen).
    """

    original_bytes: bytes
    filename: str
    doc_id: str | None = None
    collection_id: str | None = None
    metadata_fields: list | None = None
    doc_user_meta: dict | None = None


__all__ = ["IngestInput", "IngestOutput"]
