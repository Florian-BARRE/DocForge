# ====== Code Summary ======
# The asynchronous granular collection-config snippet export/apply resource: the awaiting shell over
# the shared ``_SnippetsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.snippets import CollectionSnippet, SnippetImportResult, SnippetKind
from .._base import AsyncResource
from .specs import _SnippetsSpecs


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
