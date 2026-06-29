# ====== Code Summary ======
# IndexStep — the index phase of the embed_index (S6) stage. It opens a Postgres session LOCALLY
# from deps.postgres (the session is never a context key, so it never outlives the stage), consumes
# the embed artifacts the EmbedStep stashed, and delegates to S6EmbedIndexStage.index (ensure
# collection, assemble named vectors, upsert the lean multi-vector points to Qdrant, persist all
# chunks to Postgres), writing the S6Result back. The collection_id gate (run embed_index only when
# a collection is set) is enforced UPSTREAM by the worker hooks (should_run), not here.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from .embed_step import EMBED_ARTIFACTS_KEY

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage


class IndexStep(IngestStep):
    """
    Native index step — opens a local Postgres session and runs the Qdrant upsert + PG persist.

    Reads ``ctx.aux["embed_artifacts"]`` + ``chunks``/``collection_id``/``metadata_fields``/
    ``doc_meta``; writes ``embed_result``.
    """

    KEY: ClassVar[str] = "index"
    NAME: ClassVar[str] = "Index"
    DESCRIPTION: ClassVar[str] = (
        "Upsert multi-vector points to Qdrant and persist chunks to Postgres (both idempotent)."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = (EMBED_ARTIFACTS_KEY, "chunks", "collection_id", "metadata_fields", "doc_meta")
    PRODUCES: ClassVar[tuple[str, ...]] = ("embed_result",)

    def __init__(self, embed_indexer: "S6EmbedIndexStage") -> None:
        """
        Wire the step around the embed+index implementation.

        Args:
            embed_indexer (S6EmbedIndexStage): The implementation whose ``index`` phase is run here.
        """
        IngestStep.__init__(self)
        self._embed_indexer = embed_indexer

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Open a local Postgres session, run the index phase, and write the S6Result.

        The session is opened from ``ctx.deps.postgres`` so it never outlives the stage and is
        never carried on the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Read the embed artifacts the EmbedStep stashed (None ⇒ no chunks → empty result).
        artifacts = ctx.aux.get(EMBED_ARTIFACTS_KEY)

        # 2. Open a Postgres session locally and run the index phase.
        async with ctx.deps.postgres.session() as session:
            result = await self._embed_indexer.index(
                artifacts,
                chunks=ctx.chunks,
                collection_name=ctx.collection_id,
                session=session,
                metadata_fields=ctx.metadata_fields,
                doc_meta=ctx.doc_meta,
            )

        # 3. Write the declared PRODUCES back onto the context.
        ctx.embed_result = result


__all__ = ["IndexStep"]
