# ====== Code Summary ======
# IngestRunInput — the run-wide input fed to the flow ingest pipeline (the source of every
# ``FromRunInput`` binding across the stages). It carries the original bytes + filename (read by the
# ingest stage), the target collection + metadata schema (read by embed/index), and the caller-supplied
# per-document business metadata (read by metagen). The worker driver builds one per job; the app's
# discovery never runs the pipeline, so it never needs this. A plain NodeInput subclass — its fields
# are provided directly (not resolved), so no bindings are declared.

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import NodeInput


class IngestRunInput(NodeInput):
    """
    The pipeline run input — every ``FromRunInput`` field across the ingest stages reads from here.

    Attributes:
        original_bytes (bytes): The raw original document bytes (empty -> the worker re-downloads).
        filename (str): The original upload filename (drives the format + the PDF conversion).
        doc_id (str | None): The document id (carried for lineage; the IR id is the source hash).
        collection_id (str | None): Target collection (None -> embed/index is gated off).
        metadata_fields (list | None): The collection metadata schema (feeds metagen / embed).
        doc_user_meta (dict | None): Caller-supplied per-document business metadata.
    """

    original_bytes: bytes
    filename: str
    doc_id: str | None = None
    collection_id: str | None = None
    metadata_fields: list | None = None
    doc_user_meta: dict | None = None


__all__ = ["IngestRunInput"]
