# ====== Code Summary ======
# The asynchronous document explorer (catalogue, detail, pages, IR, chunks, chunk toggles) resource:
# the awaiting shell over the shared ``_ExplorerSpecs`` builders.

# ====== Local Project Imports ======
from ...models.explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkContext,
    ChunkEnabledResult,
    ChunkInfo,
    ChunkPage,
    DocumentDetail,
    DocumentListItem,
    DocumentOutline,
    PageInfo,
)
from ...models.ir import DocumentIRModel, DocumentProvenance
from .._base import AsyncResource
from .specs import _ExplorerSpecs


class AsyncExplorer(AsyncResource, _ExplorerSpecs):
    """Asynchronous document explorer (browse, detail, IR, chunks, deletion, chunk toggles)."""

    async def list_documents(
        self, collection_id: str, limit: int | None = None, offset: int | None = None
    ) -> list[DocumentListItem]:
        """
        List a collection's documents, newest first.

        Args:
            collection_id (str): The owning collection's UUID.
            limit (int | None): Max documents to return; the server default when None.
            offset (int | None): Documents to skip (paging); the first page when None.

        Returns:
            list[DocumentListItem]: One row per document.
        """
        return await self._transport.request(
            self._list_documents_spec(collection_id, limit, offset), list[DocumentListItem]
        )

    async def get_document(self, document_id: str) -> DocumentDetail:
        """
        Fetch one document's full facts and resolved metadata.

        Args:
            document_id (str): The document's UUID.

        Returns:
            DocumentDetail: The document detail.
        """
        return await self._transport.request(self._get_document_spec(document_id), DocumentDetail)

    async def get_pages(self, document_id: str) -> list[PageInfo]:
        """
        Fetch a document's pages.

        Args:
            document_id (str): The document's UUID.

        Returns:
            list[PageInfo]: One entry per page.
        """
        return await self._transport.request(self._get_pages_spec(document_id), list[PageInfo])

    async def get_ir(self, document_id: str) -> DocumentIRModel:
        """
        Fetch a document's full canonical IR (blocks, tables, figures, enrichments).

        Args:
            document_id (str): The document's UUID.

        Returns:
            DocumentIRModel: The full IR payload.
        """
        return await self._transport.request(self._get_ir_spec(document_id), DocumentIRModel)

    async def get_provenance(self, document_id: str) -> DocumentProvenance:
        """
        Fetch a document's ingestion provenance — the parser/model pipeline that produced it.

        Args:
            document_id (str): The document to describe.

        Returns:
            DocumentProvenance: The pipeline version and per-stage trace (empty when the job expired).
        """
        return await self._transport.request(
            self._get_provenance_spec(document_id), DocumentProvenance
        )

    async def get_chunks(
        self,
        document_id: str,
        limit: int | None = None,
        offset: int | None = None,
        include_geometry: bool | None = None,
    ) -> list[ChunkInfo]:
        """
        Fetch a document's retrieval chunks (all of them when no paging argument is given).

        Use ``get_chunks_page`` when the document's total chunk count is also needed.

        Args:
            document_id (str): The document's UUID.
            limit (int | None): Max chunks to return (1..500); every chunk when None.
            offset (int | None): Chunks to skip; 0 when None.
            include_geometry (bool | None): False drops ``block_ids``/``page`` (lean); the server
                default (geometry included) when None.

        Returns:
            list[ChunkInfo]: One entry per chunk.
        """
        spec = self._get_chunks_spec(document_id, limit, offset, include_geometry)
        return await self._transport.request(spec, list[ChunkInfo])

    async def get_chunks_page(
        self,
        document_id: str,
        limit: int | None = None,
        offset: int | None = None,
        include_geometry: bool | None = None,
    ) -> ChunkPage:
        """
        Fetch a window of a document's chunks together with the document's total chunk count.

        Args:
            document_id (str): The document's UUID.
            limit (int | None): Max chunks to return (1..500); every chunk when None.
            offset (int | None): Chunks to skip; 0 when None.
            include_geometry (bool | None): False drops ``block_ids``/``page`` (lean).

        Returns:
            ChunkPage: The chunks plus ``total`` (from the ``X-Total-Count`` header).
        """
        spec = self._get_chunks_spec(document_id, limit, offset, include_geometry)
        items, total = await self._transport.request_with_total(spec, list[ChunkInfo])
        return ChunkPage(items=items, total=total)

    async def get_outline(self, document_id: str) -> DocumentOutline:
        """
        Fetch a document's heading outline - the cheap table of contents.

        Args:
            document_id (str): The document's UUID.

        Returns:
            DocumentOutline: The headings with their 1-based page and first chunk id.
        """
        return await self._transport.request(self._get_outline_spec(document_id), DocumentOutline)

    async def get_chunk_context(
        self, chunk_id: str, before: int | None = None, after: int | None = None
    ) -> ChunkContext:
        """
        Fetch a chunk together with its neighbours in the same document.

        Args:
            chunk_id (str): The chunk to read around.
            before (int | None): Chunks before the target (0..5); server default (1) when None.
            after (int | None): Chunks after the target (0..5); server default (1) when None.

        Returns:
            ChunkContext: The window in chunk_index order, the target flagged ``is_target``.
        """
        spec = self._get_chunk_context_spec(chunk_id, before, after)
        return await self._transport.request(spec, ChunkContext)

    async def delete_document(self, document_id: str) -> None:
        """
        Delete a document and everything derived from it.

        Args:
            document_id (str): The document to delete.
        """
        return await self._transport.request(self._delete_document_spec(document_id), type(None))

    async def set_chunk_enabled(self, chunk_id: str, enabled: bool) -> ChunkEnabledResult:
        """
        Toggle one chunk's searchability.

        Args:
            chunk_id (str): The chunk to toggle.
            enabled (bool): True to make searchable, False to hide.

        Returns:
            ChunkEnabledResult: The recomputed effective state and whether a re-embed is needed.
        """
        return await self._transport.request(
            self._set_chunk_enabled_spec(chunk_id, enabled), ChunkEnabledResult
        )

    async def set_chunks_enabled(self, patch: BulkChunkEnabledPatch) -> BulkChunkEnabledResponse:
        """
        Toggle several chunks' searchability to the same state in one call.

        Args:
            patch (BulkChunkEnabledPatch): The chunk ids and the state to apply.

        Returns:
            BulkChunkEnabledResponse: Per-chunk outcomes plus any ids that did not resolve.
        """
        return await self._transport.request(
            self._set_chunks_enabled_spec(patch), BulkChunkEnabledResponse
        )
