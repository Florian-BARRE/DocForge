# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_snippets.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous granular collection-config snippet export/apply resource: the blocking shell over
# the shared ``_SnippetsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.snippets import CollectionSnippet, SnippetImportResult, SnippetKind
from .._base import SyncResource
from .specs import _SnippetsSpecs


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
