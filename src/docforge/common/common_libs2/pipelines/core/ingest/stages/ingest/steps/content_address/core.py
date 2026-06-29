# ====== Code Summary ======
# IngestStageIngestStepContentAddress — the first ingest step. It content-addresses the original
# (SHA-256), assigns the effective document id, resolves the original format from the filename, and
# uploads the original bytes to the object store under ``originals/{source_hash}``. It declares the
# object store as its only required service; the convert/probe steps consume its output downstream.

# ====== Standard Library Imports ======
import hashlib
import uuid

# ====== Internal Project Imports ======
from common_libs2.pipelines import NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ..base import IngestStageIngestStepBase
from .context import IngestStageIngestStepContentAddressContext
from .errors import IngestStageIngestStepContentAddressError
from .io import (
    IngestStageIngestStepContentAddressInput,
    IngestStageIngestStepContentAddressOutput,
)

# Minimal extension -> MIME map (the real step would delegate to a shared MIME helper).
_MIME_BY_FORMAT: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "html": "text/html",
}


class IngestStageIngestStepContentAddress(IngestStageIngestStepBase):
    """
    Content-address the original and upload it to the object store.

    Reads the original bytes / filename / doc id from its parent stage input; writes the content
    address, the effective doc id, the resolved format, and the original object-store key.
    """

    SPEC = NodeSpec(
        key="content_address",
        name="Content-address",
        description="SHA-256 content address, doc id assignment, and original upload.",
    )
    Input = IngestStageIngestStepContentAddressInput
    Output = IngestStageIngestStepContentAddressOutput
    Context = IngestStageIngestStepContentAddressContext
    Error = IngestStageIngestStepContentAddressError
    REQUIRES = (ServiceRef(name="object_store", description="Content-addressed blob store."),)

    async def execute(
        self, ctx: IngestStageIngestStepContentAddressContext
    ) -> IngestStageIngestStepContentAddressOutput:
        """
        Content-address the original, upload it, and return the addressing result.

        Args:
            ctx (IngestStageIngestStepContentAddressContext): Typed input + the object store.

        Returns:
            IngestStageIngestStepContentAddressOutput: doc id + content address + format + key.

        Raises:
            IngestStageIngestStepContentAddressError: When the original upload fails.
        """
        # 1. Resolve the effective doc id (mint one only when none was provided).
        doc_id = ctx.input.doc_id or str(uuid.uuid4())

        # 2. Content-address the bytes and resolve the original format + object-store key.
        source_hash = hashlib.sha256(ctx.input.original_bytes).hexdigest()
        original_format = ctx.input.filename.rsplit(".", 1)[-1].lower() if "." in ctx.input.filename else ""
        original_key = f"originals/{source_hash}"
        self.logger.info(
            f"Content-address: doc_id={doc_id} format={original_format!r} "
            f"size={len(ctx.input.original_bytes)} sha256={source_hash[:12]}…"
        )

        # 3. Upload the original — a failure must surface as this step's typed error.
        content_type = _MIME_BY_FORMAT.get(original_format, "application/octet-stream")
        try:
            await ctx.object_store.upload(original_key, ctx.input.original_bytes, content_type)
        except Exception as exc:
            self.logger.error(f"Original upload failed for {original_key!r}: {exc}")
            raise IngestStageIngestStepContentAddressError(
                f"Failed to upload original {original_key!r}.",
                node_key=self.key,
                cause=exc,
            ) from exc

        # 4. Return the addressing result for the downstream steps.
        return IngestStageIngestStepContentAddressOutput(
            doc_id=doc_id,
            source_hash=source_hash,
            original_format=original_format,
            original_key=original_key,
        )


__all__ = ["IngestStageIngestStepContentAddress"]
