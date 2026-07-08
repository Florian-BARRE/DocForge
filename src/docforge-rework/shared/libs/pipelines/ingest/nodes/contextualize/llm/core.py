# ====== Code Summary ======
# The llm contextualizer — Anthropic-style contextual retrieval: for each chunk, a model
# reads a document view (full / the chunk's section siblings / a neighbour window — all built
# from the CHUNKS themselves, no IR needed) and writes a 1-2 sentence situating snippet appended
# to the chunk's context. The FULL view is built once per run (it is chunk-independent); calls
# are bounded by an internal semaphore; a per-chunk MODEL failure keeps the chunk raw by default
# (best-effort enhancement — a view-building bug, by contrast, surfaces loudly).

# ====== Standard Library Imports ======
import asyncio

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatHelpers
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk

# ====== Local Project Imports ======
from ..base import BaseContextualizerNode, ContextualizerConsumes, ContextualizeViewHelpers
from .config import ContextualizerLlmConfig, DocumentScope, OnChunkError


@NodeRegistry.register("contextualize")
class ContextualizerLlmNode(BaseContextualizerNode):
    """Situate each chunk in its document through a model — the retrieval-quality heavyweight."""

    KIND = "llm"
    NAME = "LLM context"
    SUMMARY = "A model writes a short snippet situating each chunk in its document."
    HOW_IT_WORKS = (
        "For each chunk, hands the model a document view (full text, the chunk's section, or a "
        "neighbour window — built from the chunks) plus the chunk itself, and appends the "
        "model's 1-2 situating sentences to the chunk's context. Calls run concurrently under "
        "an internal bound; a failing chunk stays raw (keep_raw) or fails the node (fail)."
    )
    Config = ContextualizerLlmConfig

    def __scoped_view(self, index: int, chunks: list[Chunk], full_view: str | None) -> str:
        """The document text the model reads to situate chunks[index] (scope rules + fallback)."""
        config: ContextualizerLlmConfig = self.config
        return ContextualizeViewHelpers.scoped_view(
            index, chunks, config.document_scope, config.window_chunks,
            config.max_document_words, full_view,
        )

    async def __situate_guarded(
        self, index: int, chunks: list[Chunk], full_view: str | None
    ) -> str | None:
        """One situating call; only the MODEL call is guarded by the degradation policy."""
        config: ContextualizerLlmConfig = self.config
        # 1. Build the view OUTSIDE the guard — a bug here must surface, not degrade silently.
        view = self.__scoped_view(index, chunks, full_view)
        # 2. The model call degrades per chunk: a transient failure never fails the document.
        try:
            return await self._situate(view, chunks[index].text)
        except Exception as exc:
            if config.on_error == OnChunkError.FAIL:
                raise
            self.logger.warning(
                f"Contextualizer '{self.KIND}' kept chunk '{chunks[index].chunk_id}' raw: "
                f"{type(exc).__name__}: {exc}"
            )
            return None

    async def _situate(self, document: str, chunk_text: str) -> str:
        """Ask the model for the situating snippet (overridable hook)."""
        config: ContextualizerLlmConfig = self.config
        model = OpenAICompatHelpers.chat(
            config, temperature=config.temperature, max_tokens=config.max_tokens
        )
        answer = await model.ainvoke(
            ContextualizeViewHelpers.situate_messages(config.system_prompt, document, chunk_text)
        )
        return str(answer.content)

    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """The per-chunk hook contract — one guarded situating call."""
        return await self.__situate_guarded(index, chunks, None)

    async def _contextualize(
        self, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> list[Chunk]:
        """Batch override: the FULL view precomputed once, calls under a run-scoped bound."""
        config: ContextualizerLlmConfig = self.config
        # 1. The full view is chunk-independent — O(n) once instead of O(n²) per chunk.
        full_view = (
            ContextualizeViewHelpers.full_view(chunks, config.max_document_words)
            if config.document_scope == DocumentScope.FULL and chunks
            else None
        )
        semaphore = asyncio.Semaphore(config.max_concurrency)

        async def bounded(index: int) -> str | None:
            async with semaphore:
                return await self.__situate_guarded(index, chunks, full_view)

        # 2. Situate every chunk under the concurrency bound; append the answers.
        pieces = await asyncio.gather(*(bounded(index) for index in range(len(chunks))))
        return [self._with_context(chunk, piece) for chunk, piece in zip(chunks, pieces, strict=True)]


__all__ = ["ContextualizerLlmNode"]
