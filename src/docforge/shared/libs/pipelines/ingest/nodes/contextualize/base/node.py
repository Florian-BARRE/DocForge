# ====== Code Summary ======
# BaseContextualizerNode — the abstract base of every contextualize method. The shared frame:
# take the chunks, compute each one's context piece, append it to the chunk's accumulated
# ``context`` (as a COPY — instances are shared), relay the list. Two override levels:
#   - `_context_for(index, chunks, data)` — the REQUIRED per-chunk hook (the method's piece);
#     the default `_contextualize` maps it over every chunk (fine for local methods).
#   - `_contextualize(chunks, data)` — optionally overridden by methods that manage their own
#     concurrency (the llm method bounds its API calls with a run-scoped semaphore).

# ====== Standard Library Imports ======
import asyncio
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import Chunk

# ====== Local Project Imports ======
from .io import ContextualizerConsumes, ContextualizerProduces


class BaseContextualizerNode(ActionNode):
    """Abstract contextualize method: chunks in, chunks out with their context grown."""

    Consumes = ContextualizerConsumes
    Produces = ContextualizerProduces

    @staticmethod
    def _with_context(chunk: Chunk, piece: str | None, joiner: str = "\n") -> Chunk:
        """Append a context piece to a chunk under ``joiner`` — always a COPY, raw text untouched."""
        if not piece or not piece.strip():
            return chunk
        piece = piece.strip()
        context = f"{chunk.context}{joiner}{piece}" if chunk.context else piece
        return chunk.model_copy(update={"context": context})

    def _context_joiner(self) -> str:
        """Separator this method's piece attaches under the accumulated context with (newline by
        default; a trail method joins with its own separator to keep ONE continuous prefix line)."""
        return "\n"

    @abstractmethod
    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """Per-chunk hook — what this method adds to chunks[index] (None = nothing). ``data``
        carries the method's extra slots when its Consumes extends the family face."""
        ...

    async def _contextualize(
        self, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> list[Chunk]:
        """Batch hook — the default maps the per-chunk hook over every chunk."""
        pieces = await asyncio.gather(
            *(self._context_for(index, chunks, data) for index in range(len(chunks)))
        )
        joiner = self._context_joiner()
        return [
            self._with_context(chunk, piece, joiner)
            for chunk, piece in zip(chunks, pieces, strict=True)
        ]

    async def run(self, data: ContextualizerConsumes) -> ContextualizerProduces:
        """
        Grow every chunk's retrieval context with this method's piece.

        Args:
            data (ContextualizerConsumes): The chunks (raw or already contextualised).

        Returns:
            ContextualizerProduces: The same chunks, context grown, raw text untouched.
        """
        # 1. Delegate to the method (per-chunk by default, batch when overridden). strict: a
        #    batch override returning a different-length list is a bug that must surface.
        chunks = await self._contextualize(list(data.chunks), data)
        enriched = sum(
            1 for before, after in zip(data.chunks, chunks, strict=True) if after is not before
        )
        self.logger.debug(
            f"Contextualizer '{self.KIND}' enriched {enriched}/{len(chunks)} chunk(s)"
        )
        return ContextualizerProduces(chunks=chunks)


__all__ = ["BaseContextualizerNode"]
