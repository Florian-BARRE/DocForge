# ====== Code Summary ======
# The explorer resource — the READ surface over one collection's documents (catalogue, detail, pages,
# IR, chunks), plus deletion and the chunk searchability toggles (single + bulk). The full document IR
# view (get_ir) is grouped here since it is a per-document read. All URL/body logic lives once in the
# pure _ExplorerSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkContext,
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    ChunkPage,
    DocumentDetail,
    DocumentListItem,
    DocumentOutline,
    PageInfo,
)
from ..models.ir import DocumentIRModel, DocumentProvenance
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _ExplorerSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the explorer endpoints — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"
    _DOCUMENTS_PATH = "/documents"
    _CHUNKS_PATH = "/chunks"

    def _list_documents_spec(
        self, collection_id: str, limit: int | None = None, offset: int | None = None
    ) -> RequestSpec:
        """
        Build the spec for listing a collection's documents.

        Args:
            collection_id (str): The owning collection's UUID.
            limit (int | None): Max documents to return; omitted from the query when None.
            offset (int | None): Documents to skip; omitted from the query when None.

        Returns:
            RequestSpec: A GET on the collection's documents catalogue.
        """
        return RequestSpec(
            "GET",
            f"{self._COLLECTIONS_PATH}/{collection_id}/documents",
            params={"limit": limit, "offset": offset},
        )

    def _get_document_spec(self, document_id: str) -> RequestSpec:
        """
        Build the spec for fetching one document's detail.

        Args:
            document_id (str): The document's UUID.

        Returns:
            RequestSpec: A GET on the document resource.
        """
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}")

    def _get_pages_spec(self, document_id: str) -> RequestSpec:
        """
        Build the spec for fetching a document's pages.

        Args:
            document_id (str): The document's UUID.

        Returns:
            RequestSpec: A GET on the document's pages sub-resource.
        """
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}/pages")

    def _get_ir_spec(self, document_id: str) -> RequestSpec:
        """
        Build the spec for fetching a document's full canonical IR.

        Args:
            document_id (str): The document's UUID.

        Returns:
            RequestSpec: A GET on the document's IR sub-resource.
        """
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}/ir")

    def _get_provenance_spec(self, document_id: str) -> RequestSpec:
        """
        Build the request for a document's ingestion provenance (parser/model pipeline trace).

        Args:
            document_id (str): The document to describe.

        Returns:
            RequestSpec: A GET on the document's ``/provenance`` sub-resource.
        """
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}/provenance")

    def _get_chunks_spec(
        self,
        document_id: str,
        limit: int | None = None,
        offset: int | None = None,
        include_geometry: bool | None = None,
    ) -> RequestSpec:
        """
        Build the spec for fetching a document's chunks.

        Each optional argument is forwarded only when set, so a call that sets none is the exact
        legacy request (compatible with servers that predate pagination).

        Args:
            document_id (str): The document's UUID.
            limit (int | None): Max chunks to return (1..500).
            offset (int | None): Chunks to skip.
            include_geometry (bool | None): False drops ``block_ids``/``page`` from each chunk.

        Returns:
            RequestSpec: A GET on the document's chunks sub-resource.
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "include_geometry": None if include_geometry is None else str(include_geometry).lower(),
        }
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}/chunks", params=params)

    def _get_outline_spec(self, document_id: str) -> RequestSpec:
        """
        Build the spec for a document's heading outline (table of contents).

        Args:
            document_id (str): The document's UUID.

        Returns:
            RequestSpec: A GET on the document's ``/outline`` sub-resource.
        """
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}/outline")

    def _get_chunk_context_spec(
        self, chunk_id: str, before: int | None = None, after: int | None = None
    ) -> RequestSpec:
        """
        Build the spec for a chunk's reading window (the chunk plus its neighbours).

        Args:
            chunk_id (str): The chunk to read around.
            before (int | None): Chunks before the target (0..5); server default when None.
            after (int | None): Chunks after the target (0..5); server default when None.

        Returns:
            RequestSpec: A GET on the chunk's ``/context`` sub-resource.
        """
        return RequestSpec(
            "GET",
            f"{self._CHUNKS_PATH}/{chunk_id}/context",
            params={"before": before, "after": after},
        )

    def _delete_document_spec(self, document_id: str) -> RequestSpec:
        """
        Build the spec for deleting a document.

        Args:
            document_id (str): The document to delete.

        Returns:
            RequestSpec: A DELETE on the document resource.
        """
        return RequestSpec("DELETE", f"{self._DOCUMENTS_PATH}/{document_id}")

    def _set_chunk_enabled_spec(self, chunk_id: str, enabled: bool) -> RequestSpec:
        """
        Build the spec for toggling one chunk's searchability.

        Args:
            chunk_id (str): The chunk to toggle.
            enabled (bool): The desired searchability state.

        Returns:
            RequestSpec: A PATCH on the chunk's ``/enabled`` sub-resource.
        """
        return RequestSpec(
            "PATCH",
            f"{self._CHUNKS_PATH}/{chunk_id}/enabled",
            json=ChunkEnabledPatch(enabled=enabled).model_dump(mode="json"),
        )

    def _set_chunks_enabled_spec(self, patch: BulkChunkEnabledPatch) -> RequestSpec:
        """
        Build the spec for toggling several chunks' searchability in one call.

        Args:
            patch (BulkChunkEnabledPatch): The chunk ids and the state to apply to all of them.

        Returns:
            RequestSpec: A PATCH on the chunks collection's ``/enabled`` route.
        """
        return RequestSpec(
            "PATCH", f"{self._CHUNKS_PATH}/enabled", json=patch.model_dump(mode="json")
        )


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


class SyncExplorer(SyncResource, _ExplorerSpecs):
    """Synchronous document explorer (browse, detail, IR, chunks, deletion, chunk toggles)."""

    def list_documents(
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
        return self._transport.request(
            self._list_documents_spec(collection_id, limit, offset), list[DocumentListItem]
        )

    def get_document(self, document_id: str) -> DocumentDetail:
        """
        Fetch one document's full facts and resolved metadata.

        Args:
            document_id (str): The document's UUID.

        Returns:
            DocumentDetail: The document detail.
        """
        return self._transport.request(self._get_document_spec(document_id), DocumentDetail)

    def get_pages(self, document_id: str) -> list[PageInfo]:
        """
        Fetch a document's pages.

        Args:
            document_id (str): The document's UUID.

        Returns:
            list[PageInfo]: One entry per page.
        """
        return self._transport.request(self._get_pages_spec(document_id), list[PageInfo])

    def get_ir(self, document_id: str) -> DocumentIRModel:
        """
        Fetch a document's full canonical IR (blocks, tables, figures, enrichments).

        Args:
            document_id (str): The document's UUID.

        Returns:
            DocumentIRModel: The full IR payload.
        """
        return self._transport.request(self._get_ir_spec(document_id), DocumentIRModel)

    def get_provenance(self, document_id: str) -> DocumentProvenance:
        """
        Fetch a document's ingestion provenance — the parser/model pipeline that produced it.

        Args:
            document_id (str): The document to describe.

        Returns:
            DocumentProvenance: The pipeline version and per-stage trace (empty when the job expired).
        """
        return self._transport.request(self._get_provenance_spec(document_id), DocumentProvenance)

    def get_chunks(
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
        return self._transport.request(spec, list[ChunkInfo])

    def get_chunks_page(
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
        items, total = self._transport.request_with_total(spec, list[ChunkInfo])
        return ChunkPage(items=items, total=total)

    def get_outline(self, document_id: str) -> DocumentOutline:
        """
        Fetch a document's heading outline - the cheap table of contents.

        Args:
            document_id (str): The document's UUID.

        Returns:
            DocumentOutline: The headings with their 1-based page and first chunk id.
        """
        return self._transport.request(self._get_outline_spec(document_id), DocumentOutline)

    def get_chunk_context(
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
        return self._transport.request(spec, ChunkContext)

    def delete_document(self, document_id: str) -> None:
        """
        Delete a document and everything derived from it.

        Args:
            document_id (str): The document to delete.
        """
        return self._transport.request(self._delete_document_spec(document_id), type(None))

    def set_chunk_enabled(self, chunk_id: str, enabled: bool) -> ChunkEnabledResult:
        """
        Toggle one chunk's searchability.

        Args:
            chunk_id (str): The chunk to toggle.
            enabled (bool): True to make searchable, False to hide.

        Returns:
            ChunkEnabledResult: The recomputed effective state and whether a re-embed is needed.
        """
        return self._transport.request(
            self._set_chunk_enabled_spec(chunk_id, enabled), ChunkEnabledResult
        )

    def set_chunks_enabled(self, patch: BulkChunkEnabledPatch) -> BulkChunkEnabledResponse:
        """
        Toggle several chunks' searchability to the same state in one call.

        Args:
            patch (BulkChunkEnabledPatch): The chunk ids and the state to apply.

        Returns:
            BulkChunkEnabledResponse: Per-chunk outcomes plus any ids that did not resolve.
        """
        return self._transport.request(
            self._set_chunks_enabled_spec(patch), BulkChunkEnabledResponse
        )


__all__ = ["AsyncExplorer", "SyncExplorer"]
