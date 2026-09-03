# ====== Code Summary ======
# The collection config-SNIPPET resource — the granular, SYNCHRONOUS, config-only counterpart of the
# whole-collection `.dcexport` transfer: export one slice of a collection's configuration (pipeline /
# search / schema) as a small, secret-masked, versioned JSON wrapper, and apply an inbound snippet of
# the same kind back onto a collection. All URL/body logic lives once in the pure _SnippetsSpecs mixin
# so the async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.snippets import CollectionSnippet, SnippetImportResult, SnippetKind
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _SnippetsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the snippet endpoints — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"

    def _snippet_path(self, collection_id: str, kind: SnippetKind) -> str:
        """
        Build the API-relative path to one collection's config snippet of the given kind.

        Args:
            collection_id (str): The collection's UUID.
            kind (SnippetKind): Which config slice — ``pipeline``, ``search`` or ``schema``.

        Returns:
            str: The path to the collection's ``/snippets/{kind}`` sub-resource.
        """
        return f"{self._COLLECTIONS_PATH}/{collection_id}/snippets/{kind}"

    def _export_spec(self, collection_id: str, kind: SnippetKind) -> RequestSpec:
        """
        Build the spec for exporting one config slice as a snippet.

        Args:
            collection_id (str): The collection to export from.
            kind (SnippetKind): Which config slice to export.

        Returns:
            RequestSpec: A GET on the collection's snippet sub-resource.
        """
        return RequestSpec("GET", self._snippet_path(collection_id, kind))

    def _apply_spec(
        self, collection_id: str, kind: SnippetKind, snippet: CollectionSnippet
    ) -> RequestSpec:
        """
        Build the spec for applying an inbound snippet onto an existing collection.

        Args:
            collection_id (str): The collection to apply onto.
            kind (SnippetKind): Which config slice the snippet carries (must match the snippet body).
            snippet (CollectionSnippet): The versioned, masked config slice to apply.

        Returns:
            RequestSpec: A POST on the collection's snippet sub-resource with the snippet body.
        """
        return RequestSpec(
            "POST",
            self._snippet_path(collection_id, kind),
            json=snippet.model_dump(mode="json"),
        )


class AsyncSnippets(AsyncResource, _SnippetsSpecs):
    """Asynchronous granular collection-config snippet export/apply."""

    async def export(self, collection_id: str, kind: SnippetKind) -> CollectionSnippet:
        """
        Export ONE slice of a collection's configuration as a portable, secret-masked snippet.

        Args:
            collection_id (str): The collection to export from.
            kind (SnippetKind): Which config slice — ``pipeline``, ``search`` or ``schema``.

        Returns:
            CollectionSnippet: The versioned, masked config slice.
        """
        return await self._transport.request(
            self._export_spec(collection_id, kind), CollectionSnippet
        )

    async def apply(
        self, collection_id: str, kind: SnippetKind, snippet: CollectionSnippet
    ) -> SnippetImportResult:
        """
        Apply an inbound config snippet onto an existing collection (synchronous, config-only).

        Args:
            collection_id (str): The collection to apply onto.
            kind (SnippetKind): Which config slice the snippet carries (must match the snippet body).
            snippet (CollectionSnippet): The versioned, masked config slice to apply.

        Returns:
            SnippetImportResult: The applied kind and whether a reindex is now required.
        """
        return await self._transport.request(
            self._apply_spec(collection_id, kind, snippet), SnippetImportResult
        )


class SyncSnippets(SyncResource, _SnippetsSpecs):
    """Synchronous granular collection-config snippet export/apply."""

    def export(self, collection_id: str, kind: SnippetKind) -> CollectionSnippet:
        """
        Export ONE slice of a collection's configuration as a portable, secret-masked snippet.

        Args:
            collection_id (str): The collection to export from.
            kind (SnippetKind): Which config slice — ``pipeline``, ``search`` or ``schema``.

        Returns:
            CollectionSnippet: The versioned, masked config slice.
        """
        return self._transport.request(self._export_spec(collection_id, kind), CollectionSnippet)

    def apply(
        self, collection_id: str, kind: SnippetKind, snippet: CollectionSnippet
    ) -> SnippetImportResult:
        """
        Apply an inbound config snippet onto an existing collection (synchronous, config-only).

        Args:
            collection_id (str): The collection to apply onto.
            kind (SnippetKind): Which config slice the snippet carries (must match the snippet body).
            snippet (CollectionSnippet): The versioned, masked config slice to apply.

        Returns:
            SnippetImportResult: The applied kind and whether a reindex is now required.
        """
        return self._transport.request(
            self._apply_spec(collection_id, kind, snippet), SnippetImportResult
        )


__all__ = ["AsyncSnippets", "SyncSnippets"]
