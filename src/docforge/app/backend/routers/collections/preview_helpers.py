# ====== Code Summary ======
# CollectionPreviewHelpers — the request-shaping steps shared by the dry-run preview routes, kept out
# of preview_routes.py so the routes stay orchestration: parsing the optional candidate blob form
# field, building the inline dry-run SourceDocument, and resolving a worker-preview submission payload.

# ====== Standard Library Imports ======
import json
import uuid

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request, UploadFile
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import SourceDocument
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.preview import PreviewSourceResolver
from ...utils.upload_reader import UploadReader


class CollectionPreviewHelpers:
    """Static request-shaping helpers for the collection dry-run preview routes."""

    logger = loggerplusplus.bind(identifier="CollectionPreviewHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "CollectionPreviewHelpers is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def parse_blob(blob: str | None) -> dict | None:
        """Parse the optional candidate blob form field (a JSON object) — a 422 on malformed input."""
        # 1. No candidate → preview the collection's own stored pipeline (None tells the service so).
        if blob is None or blob.strip() == "":
            return None
        # 2. A present candidate must be a JSON object; anything else is a caller fault, not a 500.
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"blob is not valid JSON: {exc}")
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=422, detail="blob must be a JSON object.")
        return parsed

    @staticmethod
    async def resolve_source(
        file: UploadFile | None,
        document_id: str | None,
        metadata: str,
        collection_id: uuid.UUID,
        collection: Collection,
        request: Request,
        size_cap: int,
    ) -> SourceDocument:
        """
        Build the dry-run SourceDocument from an uploaded file or an existing document — reads only.

        Raises:
            HTTPException: 422 on a bad document id / metadata JSON; 404 on an unknown/foreign document.
            PreviewInputError: Oversized body or missing stored bytes (mapped to 422 by the caller).
        """
        # 1. Uploaded bytes: read under the preview size cap, no storage. Declared meta is optional JSON.
        if file is not None:
            UploadReader.reject_oversized_body(request, size_cap)
            content, _ = await UploadReader.read_capped(file, size_cap)
            try:
                declared = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
            if not isinstance(declared, dict):
                raise HTTPException(status_code=422, detail="metadata must be a JSON object.")
            return SourceDocument(
                filename=file.filename or "upload", content=content, declared_meta=declared
            )

        # 2. Existing document: it must exist AND belong to this collection (no cross-collection peek).
        try:
            doc_uuid = uuid.UUID(str(document_id))
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"document_id '{document_id}' is not a valid UUID."
            )
        document = await CONTEXT.database.documents.get(doc_uuid)
        if document is None or document.collection_id != collection.id:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found in collection {collection_id}.",
            )
        return await PreviewSourceResolver(CONTEXT.database).from_document(document, size_cap)

    @staticmethod
    async def resolve_submission(
        file: UploadFile | None,
        document_id: str | None,
        metadata: str,
        collection: Collection,
        request: Request,
        size_cap: int,
    ) -> tuple[bytes | None, dict, str, str | None]:
        """
        Resolve a worker-preview submission's payload: uploaded bytes OR a validated existing document id.

        For an uploaded file the bytes are read under the preview size cap and carried to the worker on
        the queue (no storage). For an existing document id, the document is validated to exist in THIS
        collection here (fail-fast 404 at submit) but its bytes are NOT read — the worker rehydrates them.

        Returns:
            tuple[bytes | None, dict, str, str | None]: (content | None, declared_meta, filename,
                document_id | None).

        Raises:
            HTTPException: 422 on a bad document id / metadata JSON / oversized body; 404 on an
                unknown/foreign document.
        """
        # 1. Uploaded bytes: read under the preview cap, no storage. Declared meta is optional JSON.
        if file is not None:
            UploadReader.reject_oversized_body(request, size_cap)
            content, _ = await UploadReader.read_capped(file, size_cap)
            try:
                declared = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
            if not isinstance(declared, dict):
                raise HTTPException(status_code=422, detail="metadata must be a JSON object.")
            return content, declared, file.filename or "upload", None

        # 2. Existing document: it must exist AND belong to this collection (no cross-collection peek).
        try:
            doc_uuid = uuid.UUID(str(document_id))
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"document_id '{document_id}' is not a valid UUID."
            )
        document = await CONTEXT.database.documents.get(doc_uuid)
        if document is None or document.collection_id != collection.id:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found in collection {collection.id}.",
            )
        return None, {}, document.filename, str(doc_uuid)
