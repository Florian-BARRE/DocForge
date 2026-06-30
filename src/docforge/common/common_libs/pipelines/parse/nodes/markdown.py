# ====== Code Summary ======
# ParseMarkdown — the final parse node. It serialises the canonical IR to faithful markdown and
# uploads it to the object store under a CONTENT-ADDRESSED key (sha256 of the markdown bytes), so a
# bit-identical markdown view dedups to a single blob. A degraded run (no PDF view) skips serialisation
# entirely (markdown_key=None) — there is no faithful view of a document that could not be parsed,
# exactly like the v1 path. Ported from the v1 parse markdown step; the ParseResult dataclass is gone
# (its fields — ir / markdown_key / figure_crop_keys — are now surfaced directly on the stage output).

# ====== Standard Library Imports ======
import hashlib
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)
from common_libs.storage.s3.helpers import S3Helpers


class ParseMarkdownInput(NodeInput):
    """Input of the markdown node — the patched IR + crop keys + identity (to key the md blob)."""

    ir: Annotated[DocumentIR, FromNode("figure_render", "ir")]
    figure_crop_keys: Annotated[dict[str, str], FromNode("figure_render", "figure_crop_keys")]
    source_hash: Annotated[str, FromGroupInput()]
    pdf_key: Annotated[str | None, FromGroupInput()]


class ParseMarkdownOutput(NodeOutput):
    """Output of the markdown node — the final IR + the markdown view key + the figure crop keys."""

    ir: DocumentIR
    markdown_key: str | None
    figure_crop_keys: dict[str, str]


class ParseMarkdown(ActionNode):
    """Serialise the IR to markdown, upload the view, and surface the parse artefacts."""

    Input = ParseMarkdownInput
    Output = ParseMarkdownOutput

    async def execute(self, ctx: Context) -> ParseMarkdownOutput:
        """
        Serialise + upload the markdown view (or skip it on a degraded run).

        Args:
            ctx (Context): The resolved input (IR + crop keys + identity) + object store + serialiser.

        Returns:
            ParseMarkdownOutput: The final IR + the markdown key (None when degraded) + crop keys.
        """
        ir = ctx.input.ir

        # 1. Degraded run (no PDF view) -> there is no faithful view to serialise; emit no markdown,
        #    exactly like the v1 path (the document ends with no markdown view).
        if ctx.input.pdf_key is None:
            self.logger.info(
                f"Parse done (degraded, no markdown): source_hash={ctx.input.source_hash[:12]}"
            )
            return ParseMarkdownOutput(ir=ir, markdown_key=None, figure_crop_keys={})

        # 2. Serialise the IR -> markdown and content-address the blob (sha256 of the md bytes), so a
        #    bit-identical markdown view dedups to a single object-store key.
        markdown_bytes = ctx.service("serializer").serialize(ir).encode("utf-8")
        serialize_fp = hashlib.sha256(markdown_bytes).hexdigest()
        markdown_key = S3Helpers.key_markdown(ctx.input.source_hash, serialize_fp)

        # 3. Upload the markdown view.
        await ctx.service("object_store").upload(
            key=markdown_key,
            data=markdown_bytes,
            content_type="text/markdown; charset=utf-8",
        )
        self.logger.info(
            f"Parse done: source_hash={ctx.input.source_hash[:12]} blocks={len(ir.blocks)} "
            f"figures={len(ctx.input.figure_crop_keys)} -> {markdown_key}"
        )
        return ParseMarkdownOutput(
            ir=ir, markdown_key=markdown_key, figure_crop_keys=ctx.input.figure_crop_keys
        )


__all__ = ["ParseMarkdown", "ParseMarkdownInput", "ParseMarkdownOutput"]
