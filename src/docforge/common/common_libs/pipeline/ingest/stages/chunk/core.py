# ====== Code Summary ======
# ChunkStage — the native chunk (S4) stage. Assembly-only: it DECLARES the forced ClassVars
# (matching the former s4 chunk adapter byte-for-byte) and wires its single ChunkStep around the
# injected chunking implementation. CACHE_POLICY is IDEMPOTENT_WRITE (chunk ids are stable; the PG
# upsert is idempotent), so the stage is never node-cached and needs no fingerprint override.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s4_chunk.core import S4ChunkStage

# ====== Local Project Imports ======
from .steps.chunk_step import ChunkStep


@register_stage
class ChunkStage(IngestStage):
    """
    Native chunk stage — splits the enriched IR into retrieval chunks via its single ChunkStep.

    Declares the chunk contract (identity/ordering/IO/cache/error) and assembles its step around
    the chunking implementation; the run/track/fingerprint/describe machinery is inherited.
    """

    KEY: ClassVar[str] = "chunk"
    NAME: ClassVar[str] = "Chunk"
    DESCRIPTION: ClassVar[str] = (
        "Split the enriched IR into retrieval chunks using heading-hierarchy-aware, "
        "structure-aware chunking."
    )
    AFTER: ClassVar[tuple[str, ...]] = ("enrich",)
    CONFIG: ClassVar[None] = None
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir",)
    PRODUCES: ClassVar[tuple[str, ...]] = ("s4_result", "chunks")
    CACHE_POLICY: ClassVar[CachePolicy] = CachePolicy.IDEMPOTENT_WRITE
    ON_ERROR: ClassVar[ErrorPolicy] = ErrorPolicy.FAIL_DOC

    def __init__(self, inner: S4ChunkStage) -> None:
        """
        Wire the stage around a chunking implementation and build its single step.

        Args:
            inner (S4ChunkStage): The chunking implementation. Retained as ``self._inner`` so the
                assembler/parity checks can reach it.
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [ChunkStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The single native chunk step."""
        return self._steps


__all__ = ["ChunkStage"]
