# ====== Code Summary ======
# IngestScratch — the in-flight hand-off carried between the ingest stage's steps. The ingest steps
# build up several intermediate artefacts (content-address, derived PDF, page count) that are NOT
# durable PipelineContext fields; rather than widen the context with stage-internal keys, the steps
# thread them through a single mutable scratch object stashed under ``ctx.aux[INGEST_SCRATCH_KEY]``
# (mirroring how the embed_index stage hands its vectors over via ``ctx.aux``). The final step reads
# the fully-populated scratch and assembles the durable IngestResult.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass

# Context aux key under which the ingest steps share their in-flight scratch.
INGEST_SCRATCH_KEY = "ingest_scratch"


@dataclass
class IngestScratch:
    """
    Mutable hand-off accumulated across the ingest stage's steps.

    The content-address step fills the identity + original-store fields; the convert step fills the
    derived-PDF fields; the probe step reads the whole scratch to assemble the IngestResult. Every
    field is populated by the step that owns it before the next step reads it.

    Attributes:
        doc_id (str | None): Effective document UUID (provided or freshly minted).
        source_hash (str | None): SHA-256 content address of the original bytes.
        original_format (str | None): Lowercase original file extension (no dot).
        original_key (str | None): Object-store key of the uploaded original.
        pdf_bytes (bytes | None): The derived PDF bytes (passthrough or converted).
        pdf_key (str | None): Object-store key of the uploaded derived PDF.
        page_count (int | None): Page count of the derived PDF.
    """

    doc_id: str | None = None
    source_hash: str | None = None
    original_format: str | None = None
    original_key: str | None = None
    pdf_bytes: bytes | None = None
    pdf_key: str | None = None
    page_count: int | None = None


__all__ = ["IngestScratch", "INGEST_SCRATCH_KEY"]
