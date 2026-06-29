# ====== Code Summary ======
# IngestStageContextualizeStepContextualize — the single PURE-LOGIC step of the contextualize stage
# (no provider chain, no service). It reads the chunk list + the IR from the context, mutates each
# chunk's embed_text in place (title + heading breadcrumb + body, per the injected ContextualizeConfig)
# and returns the same chunk list plus the contextualization tally.

# ====== Internal Project Imports ======
from common_libs.config.pipeline import ContextualizeConfig
from common_libs.pipelines import NodeSpec

# ====== Local Project Imports ======
from ...result import IngestStageContextualizeResult
from ..base import IngestStageContextualizeStepBase
from .context import IngestStageContextualizeStepContextualizeContext
from .errors import IngestStageContextualizeStepContextualizeError
from .helpers import IngestStageContextualizeStepContextualizeHelpers
from .io import (
    IngestStageContextualizeStepContextualizeInput,
    IngestStageContextualizeStepContextualizeOutput,
)


class IngestStageContextualizeStepContextualize(IngestStageContextualizeStepBase):
    """
    Contextualize each chunk — set embed_text from title + breadcrumb + body.

    Reads ``chunks`` + ``ir`` from its parent stage input; writes each chunk's ``embed_text`` and
    returns the chunk list plus the contextualization tally. Pure logic — requires no service.
    """

    SPEC = NodeSpec(
        key="contextualize",
        name="Contextualize",
        description="Assemble each chunk's embed_text from the doc title, breadcrumb, and body.",
    )
    Input = IngestStageContextualizeStepContextualizeInput
    Output = IngestStageContextualizeStepContextualizeOutput
    Context = IngestStageContextualizeStepContextualizeContext
    Error = IngestStageContextualizeStepContextualizeError

    def __init__(self, config: ContextualizeConfig) -> None:
        """
        Wire the step around its contextualization config.

        Args:
            config (ContextualizeConfig): Header-template controls (toggles + separators).
        """
        super().__init__()
        self._config = config

    async def execute(
        self, ctx: IngestStageContextualizeStepContextualizeContext
    ) -> IngestStageContextualizeStepContextualizeOutput:
        """
        Assemble each chunk's embed_text and return the contextualized chunks plus the tally.

        Args:
            ctx (IngestStageContextualizeStepContextualizeContext): Typed input (chunks + IR).

        Returns:
            IngestStageContextualizeStepContextualizeOutput: Contextualized chunks + tally.

        Raises:
            IngestStageContextualizeStepContextualizeError: When embed_text assembly fails.
        """
        chunks = ctx.input.chunks
        ir = ctx.input.ir

        # 1. Resolve the document title once (prepended per chunk when enabled).
        doc_title = (ir.title or "").strip()
        self.logger.info(f"Contextualize started: doc_id={ir.doc_id} chunks={len(chunks)}")

        # 2. Mutate each chunk's embed_text in place, counting the non-empty ones.
        n_contextualized = 0
        try:
            for chunk in chunks:
                chunk.embed_text = IngestStageContextualizeStepContextualizeHelpers.build_embed_text(
                    chunk=chunk, doc_title=doc_title, cfg=self._config
                )
                if chunk.embed_text:
                    n_contextualized += 1
        except Exception as exc:
            self.logger.error(f"embed_text assembly failed for doc_id={ir.doc_id}: {exc}")
            raise IngestStageContextualizeStepContextualizeError(
                f"Failed to assemble embed_text for doc_id={ir.doc_id}.",
                node_key=self.key,
                cause=exc,
            ) from exc

        # 3. Return the same chunk list (mutated) plus the contextualization tally.
        self.logger.info(
            f"Contextualize done: doc_id={ir.doc_id} "
            f"contextualized={n_contextualized}/{len(chunks)}"
        )
        return IngestStageContextualizeStepContextualizeOutput(
            chunks=chunks,
            contextualize_result=IngestStageContextualizeResult(
                chunks=chunks, n_contextualized=n_contextualized
            ),
        )


__all__ = ["IngestStageContextualizeStepContextualize"]
