# ====== Code Summary ======
# The explorer resource — the READ surface over one collection's documents (catalogue, detail, pages,
# IR, chunks), plus deletion and the chunk searchability toggles (single + bulk). The full document IR
# view (get_ir) is grouped here since it is a per-document read. All URL/body logic lives once in the
# pure _ExplorerSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    DocumentDetail,
    DocumentListItem,
    PageInfo,
)
from ..models.ir import DocumentIRModel, DocumentProvenance
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _ExplorerSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the explorer endpoints — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"
    _DOCUMENTS_PATH = "/documents"
    _CHUNKS_PATH = "/chunks"

    def _list_documents_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for listing a collection's documents.

        Args:
            collection_id (str): The owning collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's documents catalogue.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/documents")

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

    def _get_chunks_spec(self, document_id: str) -> RequestSpec:
        """
        Build the spec for fetching a document's chunks.

        Args:
            document_id (str): The document's UUID.

        Returns:
            RequestSpec: A GET on the document's chunks sub-resource.
        """
        return RequestSpec("GET", f"{self._DOCUMENTS_PATH}/{document_id}/chunks")

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

    async def list_documents(self, collection_id: str) -> list[DocumentListItem]:
        """
        List a collection's documents, newest first.

        Args:
            collection_id (str): The owning collection's UUID.

        Returns:
            list[DocumentListItem]: One row per document.
        """
        return await self._transport.request(
            self._list_documents_spec(collection_id), list[DocumentListItem]
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

    async def get_chunks(self, document_id: str) -> list[ChunkInfo]:
        """
        Fetch a document's retrieval chunks.

        Args:
            document_id (str): The document's UUID.

        Returns:
            list[ChunkInfo]: One entry per chunk.
        """
        return await self._transport.request(self._get_chunks_spec(document_id), list[ChunkInfo])

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

    def list_documents(self, collection_id: str) -> list[DocumentListItem]:
        """
        List a collection's documents, newest first.

        Args:
            collection_id (str): The owning collection's UUID.

        Returns:
            list[DocumentListItem]: One row per document.
        """
        return self._transport.request(
            self._list_documents_spec(collection_id), list[DocumentListItem]
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

    def get_chunks(self, document_id: str) -> list[ChunkInfo]:
        """
        Fetch a document's retrieval chunks.

        Args:
            document_id (str): The document's UUID.

        Returns:
            list[ChunkInfo]: One entry per chunk.
        """
        return self._transport.request(self._get_chunks_spec(document_id), list[ChunkInfo])

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
