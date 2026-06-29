# ====== Code Summary ======
# EmbedStep — the embed phase of the embed_index (S6) stage. It runs the embed provider chain over
# the chunk bodies + metadata-field values (delegating to S6EmbedIndexStage.embed) and stashes the
# resulting vectors (S6EmbedArtifacts) on the context for the IndexStep to consume. The embed chain
# is driven in batches with per-batch trace accumulation inside the S6 embedder, so this is modeled
# as an IngestStep delegating to embed() rather than a single-call ChainStep; describe() still emits
# a chain-kind schema (category + the embed provider choices) so the self-describing API shows the
# escalation ladder. The embed->index hand-off travels via ctx.aux["embed_artifacts"].

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.model import StepSchema
from common_libs.pipeline.ingest.stages.base.step import IngestStep
from common_libs.pipeline.bricks.chain import ChainHelpers

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage

# Context aux key carrying the embed->index hand-off (the S6EmbedArtifacts).
EMBED_ARTIFACTS_KEY = "embed_artifacts"


class EmbedStep(IngestStep):
    """
    Native embed step — runs the embed chain and stashes the vectors for the index step.

    Reads ``chunks``/``metadata_fields``/``doc_meta``; writes ``ctx.aux["embed_artifacts"]``.
    """

    KEY: ClassVar[str] = "embed"
    NAME: ClassVar[str] = "Embed"
    DESCRIPTION: ClassVar[str] = (
        "Embed chunk bodies + metadata-field values into dense/sparse vectors via the embed chain."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("chunks", "metadata_fields", "doc_meta")
    PRODUCES: ClassVar[tuple[str, ...]] = (EMBED_ARTIFACTS_KEY,)

    def __init__(self, embed_indexer: "S6EmbedIndexStage") -> None:
        """
        Wire the step around the embed+index implementation.

        Args:
            embed_indexer (S6EmbedIndexStage): The implementation whose ``embed`` phase is run here.
        """
        IngestStep.__init__(self)
        self._embed_indexer = embed_indexer

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the embed phase and stash its artifacts on the context for the index step.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Embed chunk bodies + field values (None artifacts when there are no chunks).
        artifacts = await self._embed_indexer.embed(ctx.chunks, ctx.metadata_fields, ctx.doc_meta)

        # 2. Hand the vectors to the index step via the context's scratch space.
        ctx.aux[EMBED_ARTIFACTS_KEY] = artifacts

    def describe(self) -> StepSchema:
        """
        Emit a chain-kind schema (the embed provider category + ordered provider choices).

        Returns:
            StepSchema: Chain-kind identity + IO + the embed provider ids.
        """
        return StepSchema(
            kind="chain",
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            category="embed",
            providers=[ChainHelpers.default_provider_id(p) for p in self._embed_indexer.embed_chain.providers],
        )


__all__ = ["EmbedStep", "EMBED_ARTIFACTS_KEY"]
