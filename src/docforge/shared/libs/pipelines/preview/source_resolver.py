# ====== Code Summary ======
# PreviewSourceResolver — rehydrates the SourceDocument for a dry-run of an ALREADY-INGESTED document,
# WITHOUT persisting anything: it reads the original bytes back from the object store (bounded by the
# preview size cap so a huge original never buffers whole) and the user-declared metadata, mirroring
# exactly what the worker rehydrates for a real run. The uploaded-bytes path is handled in the router
# (it owns the multipart UploadFile); this resolver covers only the "preview an existing document" case.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import SourceDocument
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from .errors import PreviewInputError


class PreviewSourceResolver(LoggerClass):
    """Rehydrates an existing document's SourceDocument (bytes + declared meta) for a dry-run."""

    def __init__(self, database: Database) -> None:
        LoggerClass.__init__(self)
        self._database = database

    async def from_document(self, document: Any, max_bytes: int) -> SourceDocument:
        """
        Rebuild the SourceDocument of an ingested document from its stored original bytes + metadata.

        Args:
            document (Any): The document row (filename + source_hash + collection_id).
            max_bytes (int): The preview size ceiling — a larger original is refused (never buffered whole).

        Returns:
            SourceDocument: The same run-input shape the worker builds for a real ingestion.

        Raises:
            PreviewInputError: The original bytes are missing from the store, or exceed the size cap.
        """
        # 1. Pull the original bytes back from the store, bounded by the preview ceiling.
        resolved = await self._database.documents.stream_blob(document.source_hash)
        if resolved is None:
            raise PreviewInputError(
                f"original bytes for document {document.id} are no longer in the store"
            )
        content = await self.__read_capped(resolved[0], max_bytes, document.id)

        # 2. Re-derive the caller-declared metadata (origin=user), resolved to field names — exactly
        #    the worker's rehydrate (a preview must admit against the same declared values).
        declared = await self.__declared_meta(document.collection_id, document.id)
        return SourceDocument(filename=document.filename, content=content, declared_meta=declared)

    async def __read_capped(self, stream: Any, max_bytes: int, document_id: uuid.UUID) -> bytes:
        """Accumulate an S3 byte-stream, aborting the instant it crosses the preview ceiling."""
        buffer = bytearray()
        async for chunk in stream:
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                raise PreviewInputError(
                    f"document {document_id} exceeds the preview size cap (> {max_bytes} bytes) — "
                    f"ingest it for the full pipeline instead of a dry-run"
                )
        return bytes(buffer)

    async def __declared_meta(
        self, collection_id: uuid.UUID, document_id: uuid.UUID
    ) -> dict[str, Any]:
        """Map the document's user-declared metadata rows to {field_name: value} (empty when none)."""
        schema = await self._database.collections.get_schema(collection_id)
        field_names = {row.id: row.field_name for row in schema}
        return {
            field_names[meta.field_id]: meta.value
            for meta in await self._database.documents.get_metadata(document_id)
            if meta.origin.value == "user" and meta.field_id in field_names
        }


__all__ = ["PreviewSourceResolver"]
