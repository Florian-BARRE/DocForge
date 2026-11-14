# ====== Code Summary ======
# PreviewReadPort — the read-only capability a preview dry-run needs to rehydrate an ALREADY-INGESTED
# document: the original bytes from the object store, the collection's metadata schema and the
# document's stored metadata rows. The pipelines package declares it and never imports the stores
# (dependency direction: services → pipelines); the app and the worker pass the ``Database`` façade,
# which satisfies it structurally (``documents`` / ``collections`` façades with these exact methods).

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol


class PreviewDocumentReads(Protocol):
    """The document-side reads a preview needs (stored bytes + declared metadata)."""

    async def stream_blob(self, content_hash: str) -> tuple[AsyncIterator[bytes], str] | None:
        """Return ``(byte stream, mime type)`` of the stored original, or None when it is gone."""
        ...

    async def get_metadata(self, document_id: uuid.UUID) -> list[Any]:
        """Return the document's stored metadata rows (``field_id``, ``origin``, ``value``)."""
        ...


class PreviewCollectionReads(Protocol):
    """The collection-side reads a preview needs (the metadata field schema)."""

    async def get_schema(self, collection_id: uuid.UUID) -> list[Any]:
        """Return the collection's metadata-field rows (``id``, ``field_name``)."""
        ...


class PreviewReadPort(Protocol):
    """Read-only store access of a dry-run preview, injected by the app and the worker."""

    documents: PreviewDocumentReads
    collections: PreviewCollectionReads


__all__ = ["PreviewReadPort", "PreviewDocumentReads", "PreviewCollectionReads"]
