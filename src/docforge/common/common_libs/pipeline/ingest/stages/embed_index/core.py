# ====== Code Summary ======
# EmbedIndexStage — the native embed_index (S6) stage, decomposed into TWO real steps:
# EmbedStep (run the embed provider chain → vectors) then IndexStep (Qdrant upsert + Postgres
# persist). Assembly-only: it DECLARES the forced ClassVars (matching the former s6 adapter
# byte-for-byte) and wires the two steps around the injected embed+index implementation. The
# embed→index hand-off travels through ctx.aux; IndexStep opens its own local Postgres session.
# CACHE_POLICY is IDEMPOTENT_WRITE (PG + Qdrant upserts), so the stage is never node-cached. The
# collection_id gate is enforced by the worker hooks (should_run), not here. describe() is the
# inherited recursion over the two steps (EmbedStep emits a chain schema; IndexStep a plain step).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage

# ====== Local Project Imports ======
from .steps.embed_step import EmbedStep
from .steps.index_step import IndexStep


@register_stage
class EmbedIndexStage(IngestStage):
    """
    Native embed+index stage — embeds (EmbedStep) then indexes (IndexStep) in two real steps.

    Declares the embed_index contract (identity/ordering/IO/cache/error). The single executing
    inner implementation is shared by both steps; the embed→index vectors flow through the context.
    """

    KEY: ClassVar[str] = "embed_index"
    NAME: ClassVar[str] = "Embed & Index"
    DESCRIPTION: ClassVar[str] = (
        "Embed chunk bodies + metadata fields, upsert multi-vector points to Qdrant, and persist "
        "chunks to Postgres."
    )
    AFTER: ClassVar[tuple[str, ...]] = ("metagen",)
    CONFIG: ClassVar[None] = None
    CONSUMES: ClassVar[tuple[str, ...]] = ("chunks", "collection_id", "metadata_fields", "doc_meta")
    PRODUCES: ClassVar[tuple[str, ...]] = ("s6_result",)
    CACHE_POLICY: ClassVar[CachePolicy] = CachePolicy.IDEMPOTENT_WRITE
    ON_ERROR: ClassVar[ErrorPolicy] = ErrorPolicy.FAIL_DOC

    def __init__(self, inner: S6EmbedIndexStage) -> None:
        """
        Wire the stage around an embed+index implementation and build its two steps.

        Args:
            inner (S6EmbedIndexStage): The embed+index implementation. Retained as ``self._inner`` so
                the assembler/parity checks can reach its embed chain. Both steps share this instance
                (the embedder's per-run trace accumulator persists from EmbedStep into IndexStep).
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [EmbedStep(inner), IndexStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The two native steps: embed (provider chain) then index (Qdrant upsert + PG persist)."""
        return self._steps


__all__ = ["EmbedIndexStage"]
