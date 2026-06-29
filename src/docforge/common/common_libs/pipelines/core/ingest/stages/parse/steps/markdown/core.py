# ====== Code Summary ======
# IngestStageParseStepMarkdown — the final parse step. It serialises the canonical IR to faithful
# markdown and uploads it to the object store under a content-addressed key (sha256 of the markdown
# bytes), then assembles the durable ParseResult (the parse stage's output contract consumed by enrich
# + the worker node-cache codec). A degraded (no-parse) run skips serialisation entirely
# (markdown_key=None), exactly like the legacy path.

# ====== Standard Library Imports ======
import hashlib

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ...result import ParseResult
from ..base import IngestStageParseStepBase
from .context import IngestStageParseStepMarkdownContext
from .errors import IngestStageParseStepMarkdownError
from .io import IngestStageParseStepMarkdownInput, IngestStageParseStepMarkdownOutput


class IngestStageParseStepMarkdown(IngestStageParseStepBase):
    """
    Serialise the IR to markdown, upload it, and emit the ParseResult.

    Reads the patched IR + figure crop keys (figure-render), the degraded flag (parse), and the source
    hash (stage input); writes the durable ParseResult + the final IR.
    """

    SPEC = NodeSpec(
        key="markdown",
        name="Render markdown",
        description=(
            "Serialise the canonical IR to faithful markdown, upload it to the object store, and "
            "assemble the parse result."
        ),
    )
    Input = IngestStageParseStepMarkdownInput
    Output = IngestStageParseStepMarkdownOutput
    Context = IngestStageParseStepMarkdownContext
    Error = IngestStageParseStepMarkdownError
    REQUIRES = (
        ServiceRef(name="object_store", description="Content-addressed blob store."),
        ServiceRef(name="serializer", description="Canonical IR -> markdown serialiser."),
    )

    async def execute(
        self, ctx: IngestStageParseStepMarkdownContext
    ) -> IngestStageParseStepMarkdownOutput:
        """
        Serialise + upload the markdown view and assemble the durable ParseResult.

        Args:
            ctx (IngestStageParseStepMarkdownContext): Typed input + object store + serialiser.

        Returns:
            IngestStageParseStepMarkdownOutput: The ParseResult + the final IR.

        Raises:
            IngestStageParseStepMarkdownError: When the markdown upload fails.
        """
        ir = ctx.input.ir

        # 1. Degraded (no-parse) outcome: there is no IR to serialise — emit markdown_key=None,
        # exactly like the legacy path (the document ends "done" with no markdown view).
        if ctx.input.degraded:
            self.logger.info(f"Parse done (degraded, no markdown): source_hash={ctx.input.source_hash[:12]}")
            return IngestStageParseStepMarkdownOutput(
                parse_result=ParseResult(ir=ir, markdown_key=None, figure_crop_keys={}), ir=ir
            )

        # 2. Serialise the IR -> markdown and content-address the blob (sha256 of the md bytes), so a
        # bit-identical markdown view dedups to a single object-store key.
        markdown_text = ctx.serializer.serialize(ir)
        markdown_bytes = markdown_text.encode("utf-8")
        serialize_fp = hashlib.sha256(markdown_bytes).hexdigest()
        markdown_key = S3Helpers.key_markdown(ctx.input.source_hash, serialize_fp)

        # 3. Upload the markdown view — a failure must surface as this step's typed error.
        try:
            await ctx.object_store.upload(
                key=markdown_key,
                data=markdown_bytes,
                content_type="text/markdown; charset=utf-8",
            )
        except Exception as exc:
            self.logger.error(f"Markdown upload failed for {markdown_key!r}: {exc}")
            raise IngestStageParseStepMarkdownError(
                f"Failed to upload markdown {markdown_key!r}.",
                node_key=self.key,
                cause=exc,
            ) from exc
        self.logger.debug(f"Uploaded markdown -> {markdown_key}")

        # 4. Assemble + emit the durable parse result (the output contract consumed by enrich).
        parse_result = ParseResult(
            ir=ir, markdown_key=markdown_key, figure_crop_keys=ctx.input.figure_crop_keys
        )
        self.logger.info(
            f"Parse done: source_hash={ctx.input.source_hash[:12]} blocks={len(ir.blocks)} "
            f"figures={len(ctx.input.figure_crop_keys)}"
        )
        return IngestStageParseStepMarkdownOutput(parse_result=parse_result, ir=ir)


__all__ = ["IngestStageParseStepMarkdown"]
