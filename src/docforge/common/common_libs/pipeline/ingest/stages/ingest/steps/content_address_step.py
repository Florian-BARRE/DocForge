# ====== Code Summary ======
# ContentAddressStep — the first ingest step. It content-addresses the original file (SHA-256),
# assigns the effective document id, resolves the original's extension, and uploads the original
# bytes to the object store at ``originals/{source_hash}``. It writes the durable ``source_hash``
# context field and seeds the cross-step IngestScratch with the identity + original-store artefacts.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ..helpers import IngestHelpers
from ..scratch import INGEST_SCRATCH_KEY, IngestScratch

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.storage.s3.client import S3Client


class ContentAddressStep(IngestStep):
    """
    Native ingest step — content-addresses the original and uploads it to the object store.

    Reads ``original_bytes``/``filename``/``doc_id``; writes ``source_hash`` and seeds
    ``ctx.aux["ingest_scratch"]`` (doc id, source hash, original format + key) for the later steps.
    """

    KEY: ClassVar[str] = "content_address"
    NAME: ClassVar[str] = "Content-address"
    DESCRIPTION: ClassVar[str] = (
        "Compute the SHA-256 content address, assign the document id, and upload the original "
        "file to the object store."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("original_bytes", "filename", "doc_id")
    PRODUCES: ClassVar[tuple[str, ...]] = ("source_hash", INGEST_SCRATCH_KEY)

    def __init__(self, s3: "S3Client") -> None:
        """
        Wire the step around the object-store client.

        Args:
            s3 (S3Client): SeaweedFS S3-compatible client for the original upload.
        """
        IngestStep.__init__(self)
        self._s3 = s3

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Content-address the original, upload it, and seed the ingest scratch.

        Args:
            ctx (PipelineContext): The mutable run accumulator.

        Raises:
            Exception: Re-raises any object-store upload failure (the stage is FAIL_DOC).
        """
        # 1. Resolve the effective doc id. A None here would orphan the pre-created Postgres row,
        # so a freshly-minted id only happens when no id was provided (parity with the legacy S0).
        doc_id = str(ctx.doc_id) if ctx.doc_id is not None else str(uuid.uuid4())

        # 2. Content-address the original bytes and resolve its extension + object-store key.
        source_hash = IngestHelpers.sha256(ctx.original_bytes)
        original_format = IngestHelpers.extract_extension(ctx.filename)
        original_key = S3Helpers.key_original(source_hash)
        self.logger.info(
            f"Ingest content-address: doc_id={doc_id} filename={ctx.filename!r} "
            f"format={original_format} size={len(ctx.original_bytes)} bytes sha256={source_hash[:12]}…"
        )

        # 3. Upload the original — a failure must fail the document (FAIL_DOC), so log + re-raise.
        try:
            await self._s3.upload(
                key=original_key,
                data=ctx.original_bytes,
                content_type=IngestHelpers.mime_type(original_format),
            )
        except Exception as exc:
            self.logger.error(f"Original upload failed for {original_key!r}: {exc}")
            raise
        self.logger.debug(f"Uploaded original → {original_key}")

        # 4. Write the durable source_hash + seed the cross-step scratch.
        ctx.source_hash = source_hash
        ctx.aux[INGEST_SCRATCH_KEY] = IngestScratch(
            doc_id=doc_id,
            source_hash=source_hash,
            original_format=original_format,
            original_key=original_key,
        )


__all__ = ["ContentAddressStep"]
