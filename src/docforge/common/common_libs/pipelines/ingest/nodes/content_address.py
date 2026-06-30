# ====== Code Summary ======
# The content-address node — the first elementary action of the ingest stage. It computes the original
# file's content address (sha256), derives its format from the filename, and stores the original blob
# in the object store under its content-addressed key. One self-contained file: its typed Input
# (bound to the run input), its typed Output, and its logic. Domain/storage coupling stays in this leaf.

# ====== Standard Library Imports ======
import hashlib
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import ActionNode, Context, FromRunInput, NodeInput, NodeOutput
from common_libs.storage.s3.helpers import S3Helpers


class IngestContentAddressInput(NodeInput):
    """Input of the content-address node — the raw original bytes + its filename (from the run input)."""

    original_bytes: Annotated[bytes, FromRunInput()]
    filename: Annotated[str, FromRunInput()]


class IngestContentAddressOutput(NodeOutput):
    """Output of the content-address node — the content address + format + the stored original key."""

    source_hash: str
    original_format: str
    original_key: str


class IngestContentAddress(ActionNode):
    """Content-address the original: sha256 + format + store the blob under its content-addressed key."""

    Input = IngestContentAddressInput
    Output = IngestContentAddressOutput

    async def execute(self, ctx: Context) -> IngestContentAddressOutput:
        """
        Compute the content address, derive the format, and store the original blob.

        Args:
            ctx (Context): Carries the resolved input (bytes + filename) and the object store service.

        Returns:
            IngestContentAddressOutput: The source hash, the original format, and the stored key.
        """
        # 1. Content address (sha256) + format from the filename extension.
        data = ctx.input.original_bytes
        source_hash = hashlib.sha256(data).hexdigest()
        filename = ctx.input.filename
        original_format = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"

        # 2. Store the original blob under its content-addressed key.
        original_key = S3Helpers.key_original(source_hash)
        await ctx.service("object_store").upload(original_key, data)

        self.logger.info(
            f"Content-addressed doc: format={original_format!r} size={len(data)} "
            f"sha256={source_hash[:12]}."
        )
        return IngestContentAddressOutput(
            source_hash=source_hash, original_format=original_format, original_key=original_key
        )


__all__ = ["IngestContentAddress", "IngestContentAddressInput", "IngestContentAddressOutput"]
