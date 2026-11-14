# ====== Code Summary ======
# The pure ``RequestSpec`` builders of the document explorer (catalogue, detail, pages, IR, chunks,
# chunk toggles) resource — the single source of its URL/param/body logic, shared verbatim by the
# async and sync resources so their bodies differ ONLY by ``await``.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from ...models.explorer import BulkChunkEnabledPatch, ChunkEnabledPatch
from .._base import _ResourceMixin


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
