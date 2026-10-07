# ====== Code Summary ======
# DocumentReader — the read service behind the document-READING routes (outline + chunk context). It
# composes lean facade reads (heading columns, a text-free chunk index, the window's chunk rows + their
# leading-block page) with the pure OutlineBuilder / ChunkWindow, and resolves the display title the
# same way the explorer does (collection title_field value, else the parsed title). Existence checks
# return None — the route owns the 404 and the collection-scope gate.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import DisplayTitleResolver
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import Chunk, Document

# ====== Local Project Imports ======
from .chunk_window import ChunkWindow
from .models import ChunkContext, ContextChunk, DocumentOutline
from .outline_builder import OutlineBuilder


class DocumentReader(LoggerClass):
    """Build a document's outline and the context window around one of its chunks."""

    def __init__(self, database: Database) -> None:
        """
        Args:
            database (Database): The shared data facade (documents + collections reads).
        """
        LoggerClass.__init__(self)
        self._database = database

    async def _display_title(self, document: Document) -> str:
        """The collection's title_field value for this document when set, else the parsed title."""
        # 1. No configured title field → the parsed title, without any metadata read.
        collection = await self._database.collections.get(document.collection_id)
        title_field = collection.title_field if collection is not None else None
        if not title_field:
            return document.title or ""

        # 2. Name the document's metadata values, then apply the single display-title rule.
        schema = await self._database.collections.get_schema(document.collection_id)
        names = {field.id: field.field_name for field in schema}
        rows = await self._database.documents.get_metadata(document.id)
        values = {names[row.field_id]: row.value for row in rows if row.field_id in names}
        return DisplayTitleResolver.resolve(document.title, values, title_field) or ""

    @staticmethod
    def _context_chunk(
        row: Chunk, target_id: uuid.UUID, located: list[dict] | None
    ) -> ContextChunk:
        """Map one chunk row (+ its block locations, leading block first) to a lean window item."""
        page = located[0]["page"] if located else None
        return ContextChunk(
            chunk_id=str(row.id),
            chunk_index=row.chunk_index,
            text=row.text,
            page_number=None if page is None else page + 1,
            heading_path=row.heading_path or [],
            token_count=row.token_count,
            is_target=row.id == target_id,
        )

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        """Fetch a document (None when unknown)."""
        return await self._database.documents.get(document_id)

    async def locate_chunk(self, chunk_id: uuid.UUID) -> tuple[Chunk, Document] | None:
        """Fetch a chunk and its owning document (None when either is unknown)."""
        # 1. The chunk row first — an unknown id ends here.
        chunks = await self._database.documents.get_chunks_by_ids([chunk_id])
        if not chunks:
            return None

        # 2. Its document (gone only in a delete race — treated as unknown).
        document = await self._database.documents.get(chunks[0].document_id)
        return None if document is None else (chunks[0], document)

    async def outline(self, document: Document) -> DocumentOutline:
        """
        Build the document's heading outline (page + section-opening chunk per heading).

        Args:
            document (Document): The (already scope-checked) document.

        Returns:
            DocumentOutline: The outline envelope; ``headings`` is [] for a heading-less document.
        """
        # 1. Two column-only reads: the heading blocks and the text-free chunk index.
        headings = await self._database.documents.get_headings(document.id)
        chunks = await self._database.documents.get_chunk_index(document.id)

        # 2. Link and shape them, then wrap with the document facts.
        return DocumentOutline(
            document_id=str(document.id),
            display_title=await self._display_title(document),
            page_count=document.page_count,
            headings=OutlineBuilder.build(headings, chunks),
        )

    async def chunk_context(
        self, chunk: Chunk, document: Document, before: int, after: int
    ) -> ChunkContext:
        """
        Return ``chunk`` with its enabled neighbours by chunk_index.

        Args:
            chunk (Chunk): The target chunk.
            document (Document): Its (already scope-checked) owning document.
            before (int): Searchable chunks to include before the target.
            after (int): Searchable chunks to include after the target.

        Returns:
            ChunkContext: The ordered window, the target flagged ``is_target``.
        """
        # 1. Pick the window from the text-free index, then load only those rows (+ leading page).
        index = await self._database.documents.get_chunk_index(document.id)
        window_ids = [entry.id for entry in ChunkWindow.select(index, chunk.id, before, after)]
        rows = {row.id: row for row in await self._database.documents.get_chunks_by_ids(window_ids)}
        rows[chunk.id] = chunk
        locations = await self._database.documents.get_block_locations_for_chunks(window_ids)

        # 2. Shape each chunk lean, in window order (a row deleted mid-read is simply dropped).
        items = [
            self._context_chunk(rows[chunk_id], chunk.id, locations.get(str(chunk_id)))
            for chunk_id in window_ids
            if chunk_id in rows
        ]
        return ChunkContext(
            document_id=str(document.id),
            display_title=await self._display_title(document),
            chunks=items,
        )


__all__ = ["DocumentReader"]
