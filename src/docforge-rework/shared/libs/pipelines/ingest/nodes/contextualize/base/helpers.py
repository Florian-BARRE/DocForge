# ====== Code Summary ======
# ContextualizeViewHelpers — the ONE place the "document view a model reads to situate a chunk" is
# built, shared by the monolithic llm contextualizer and the externalised prep node so the two can
# never drift. It owns the three pure view operations (word-cap truncation, the chunk-independent
# FULL view, the per-chunk scoped view with its section/window fallback) plus the situating message
# composition. The FULL view is chunk-independent, so a caller builds it ONCE per run and threads it
# in — the helper never rebuilds it per chunk (no O(n²) regression).

# ====== Third-Party Library Imports ======
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import Chunk

# ====== Local Project Imports ======
from .enums import DocumentScope


class ContextualizeViewHelpers:
    """Static builders of the document view (and the situating prompt) a contextualizer model reads."""

    logger = loggerplusplus.bind(identifier="ContextualizeViewHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "ContextualizeViewHelpers is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def truncate(text: str, max_document_words: int) -> str:
        """Apply the hard word cap — a text UNDER the cap keeps its structure untouched."""
        words = text.split()
        if len(words) <= max_document_words:
            return text
        # Truncate from the start — documents introduce themselves there.
        return " ".join(words[:max_document_words])

    @classmethod
    def full_view(cls, chunks: list[Chunk], max_document_words: int) -> str:
        """The whole-document view — chunk-independent, built ONCE per run by the caller."""
        return cls.truncate("\n\n".join(chunk.text for chunk in chunks), max_document_words)

    @classmethod
    def scoped_view(
        cls,
        index: int,
        chunks: list[Chunk],
        document_scope: DocumentScope,
        window_chunks: int,
        max_document_words: int,
        full_view: str | None,
    ) -> str:
        """
        The document text the model reads to situate ``chunks[index]`` (scope rules + fallback).

        Args:
            index (int): Position of the target chunk.
            chunks (list[Chunk]): The full ordered chunk list (the view's source).
            document_scope (DocumentScope): full / section / window.
            window_chunks (int): Neighbours per side for the window scope (and section fallback).
            max_document_words (int): Hard cap on the returned text.
            full_view (str | None): The pre-built FULL view — reused for FULL scope, never rebuilt.

        Returns:
            str: The scoped, word-capped document view.
        """
        target = chunks[index]

        # 1. FULL: reuse the per-run view (never rebuild it per chunk).
        if document_scope == DocumentScope.FULL:
            return full_view if full_view is not None else cls.full_view(chunks, max_document_words)

        # 2. SECTION: the chunk's siblings; a section-less chunk falls back to the window.
        if document_scope == DocumentScope.SECTION and target.heading_path:
            members = [chunk for chunk in chunks if chunk.heading_path == target.heading_path]
        else:
            start = max(0, index - window_chunks)
            members = chunks[start : index + window_chunks + 1]
        return cls.truncate("\n\n".join(member.text for member in members), max_document_words)

    @staticmethod
    def situate_messages(system_prompt: str, document: str, chunk_text: str) -> list[AnyMessage]:
        """
        Compose the situating chat messages — the exact prompt the model answers with a snippet.

        Args:
            system_prompt (str): The situating instruction (system role).
            document (str): The document view the chunk is situated within.
            chunk_text (str): The chunk to situate.

        Returns:
            list[AnyMessage]: A SystemMessage followed by the document/chunk HumanMessage.
        """
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(f"<document>\n{document}\n</document>\n\n<chunk>\n{chunk_text}\n</chunk>")
            ),
        ]


__all__ = ["ContextualizeViewHelpers"]
