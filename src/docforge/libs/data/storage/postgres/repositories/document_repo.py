# ====== Code Summary ======
# Repository for DocumentModel: creation, status updates, retrieval, deduplication check.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Local Project Imports ======
from ..models import BlockModel, DocumentModel, StageRunModel


class DocumentRepository(LoggerClass):
    """
    Data-access layer for the ``document`` table.

    All methods require an active ``AsyncSession`` passed by the caller
    (the session lifecycle is managed by the router / pipeline runner).
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    async def list_source_hashes(self, session: AsyncSession, collection_id: uuid.UUID) -> list[str]:
        """
        Return the distinct source_hashes of a collection's documents (for blob GC).

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Target collection.

        Returns:
            list[str]: Distinct SHA-256 hex digests referenced by the collection's documents.
        """
        result = await session.execute(
            select(DocumentModel.source_hash).where(DocumentModel.collection_id == collection_id).distinct()
        )
        return [row[0] for row in result.all()]

    async def is_source_hash_shared(
        self, session: AsyncSession, source_hash: str, exclude_collection_id: uuid.UUID
    ) -> bool:
        """
        Return True if another collection still references this content-addressed blob.

        Args:
            session (AsyncSession): Active session.
            source_hash (str): SHA-256 hex digest of the blob to check.
            exclude_collection_id (uuid.UUID): The collection being deleted — excluded from the check.

        Returns:
            bool: True if at least one other collection's document references the same blob.
        """
        result = await session.execute(
            select(DocumentModel.id).where(
                DocumentModel.source_hash == source_hash,
                DocumentModel.collection_id != exclude_collection_id,
            ).limit(1)
        )
        return result.first() is not None

    async def is_source_hash_used_by_other_documents(
        self, session: AsyncSession, source_hash: str, exclude_document_id: uuid.UUID
    ) -> bool:
        """
        Return True if any OTHER document (in any collection) still references this blob.

        Used by single-document delete: the content-addressed original/derived blobs are only
        safe to remove when no other document points at the same source_hash.

        Args:
            session (AsyncSession): Active session.
            source_hash (str): SHA-256 hex digest of the blob to check.
            exclude_document_id (uuid.UUID): The document being deleted — excluded from the check.

        Returns:
            bool: True if at least one other document references the same blob.
        """
        result = await session.execute(
            select(DocumentModel.id).where(
                DocumentModel.source_hash == source_hash,
                DocumentModel.id != exclude_document_id,
            ).limit(1)
        )
        return result.first() is not None

    async def create(
        self,
        session: AsyncSession,
        *,
        collection_id: uuid.UUID,
        source_hash: str,
        filename: str,
        format: str,
        file_size: int,
        pipeline_version: str,
        user_meta: dict[str, Any] | None = None,
        implicit_meta: dict[str, Any] | None = None,
    ) -> DocumentModel:
        """
        Persist a new document record with status='pending'.

        Args:
            session (AsyncSession): Active transactional session.
            collection_id (uuid.UUID): Parent collection.
            source_hash (str): SHA-256 hex digest of the original file.
            filename (str): Original filename.
            format (str): File extension / MIME type key (e.g. "pdf", "docx").
            file_size (int): File size in bytes.
            pipeline_version (str): Pipeline version string from the collection.
            user_meta (dict | None): User-supplied metadata payload.
            implicit_meta (dict | None): Auto-extracted file-intrinsic metadata.

        Returns:
            DocumentModel: The newly created (and flushed) record.
        """
        # 1. Build the ORM instance
        doc = DocumentModel(
            collection_id=collection_id,
            source_hash=source_hash,
            filename=filename,
            format=format,
            file_size=file_size,
            pipeline_version=pipeline_version,
            user_meta=user_meta or {},
            implicit_meta=implicit_meta or {},
            status="pending",
        )

        # 2. Persist and flush to get the generated ID
        session.add(doc)
        await session.flush()

        self.logger.debug(f"Created document id={doc.id} filename={filename}")
        return doc

    async def get_by_id(
        self, session: AsyncSession, doc_id: uuid.UUID
    ) -> DocumentModel | None:
        """
        Fetch a document by its UUID.

        Args:
            session (AsyncSession): Active session.
            doc_id (uuid.UUID): Document primary key.

        Returns:
            DocumentModel | None: The record, or None if not found.
        """
        result = await session.execute(
            select(DocumentModel).where(DocumentModel.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def find_duplicate(
        self,
        session: AsyncSession,
        *,
        collection_id: uuid.UUID,
        source_hash: str,
        pipeline_version: str,
    ) -> DocumentModel | None:
        """
        Check for a previously ingested document with the same content and pipeline version.

        A match means the document was already processed (or is being processed) under
        the same config — callers should return 200 without re-queuing.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Scope the dedup check to this collection.
            source_hash (str): SHA-256 of the file.
            pipeline_version (str): Must match to be considered a true duplicate.

        Returns:
            DocumentModel | None: Existing record, or None if this is a new document.
        """
        result = await session.execute(
            select(DocumentModel).where(
                DocumentModel.collection_id == collection_id,
                DocumentModel.source_hash == source_hash,
                DocumentModel.pipeline_version == pipeline_version,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session: AsyncSession,
        doc_id: uuid.UUID,
        status: str,
        *,
        page_count: int | None = None,
        language: str | None = None,
        implicit_meta: dict[str, Any] | None = None,
    ) -> None:
        """
        Update a document's processing status and optional derived fields.

        Args:
            session (AsyncSession): Active session.
            doc_id (uuid.UUID): Document to update.
            status (str): New status (pending | processing | done | failed).
            page_count (int | None): Total page count, set after S1.
            language (str | None): Detected language, set after S1.
            implicit_meta (dict | None): Updated implicit metadata.

        Returns:
            None
        """
        # 1. Build the values dict dynamically
        values: dict[str, Any] = {"status": status}
        if page_count is not None:
            values["page_count"] = page_count
        if language is not None:
            values["language"] = language
        if implicit_meta is not None:
            values["implicit_meta"] = implicit_meta

        # 2. Execute bulk update
        await session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == doc_id)
            .values(**values)
        )

        self.logger.debug(f"Document id={doc_id} status → {status}")

    async def update_user_meta(
        self, session: AsyncSession, doc_id: uuid.UUID, user_meta: dict[str, Any]
    ) -> DocumentModel | None:
        """
        Replace a document's user metadata with the given (already-merged) payload.

        The caller is responsible for the merge/validation; this writes the final value.

        Args:
            session (AsyncSession): Active session.
            doc_id (uuid.UUID): Document to update.
            user_meta (dict): The full new user metadata.

        Returns:
            DocumentModel | None: The refreshed document, or None if it does not exist.
        """
        await session.execute(
            update(DocumentModel).where(DocumentModel.id == doc_id).values(user_meta=user_meta)
        )
        await session.flush()
        result = await session.execute(select(DocumentModel).where(DocumentModel.id == doc_id))
        return result.scalar_one_or_none()

    async def delete(self, session: AsyncSession, doc_id: uuid.UUID) -> bool:
        """
        Delete a document and all its DB rows.

        FK ON DELETE CASCADE handles block / chunk / job. stage_run has no cascade FK
        (it references document_id without a constraint), so those rows are removed first.

        Args:
            session (AsyncSession): Active transactional session.
            doc_id (uuid.UUID): Primary key of the document to delete.

        Returns:
            bool: True if a document row was deleted, False if it did not exist.
        """
        # 1. Remove orphan-prone stage_run rows for this document
        await session.execute(sa_delete(StageRunModel).where(StageRunModel.document_id == doc_id))

        # 2. Delete the document (cascades blocks/chunks/jobs)
        result = await session.execute(sa_delete(DocumentModel).where(DocumentModel.id == doc_id))
        return (result.rowcount or 0) > 0

    async def count_by_collection(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        *,
        status_filter: str | None = None,
    ) -> int:
        """
        Count documents in a collection, optionally filtered by status.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Parent collection.
            status_filter (str | None): When set, count only documents with this status.

        Returns:
            int: Total matching document count.
        """
        query = select(func.count()).select_from(DocumentModel).where(
            DocumentModel.collection_id == collection_id
        )
        if status_filter is not None:
            query = query.where(DocumentModel.status == status_filter)
        return int(await session.scalar(query) or 0)

    async def count_blocks(self, session: AsyncSession, document_id: uuid.UUID) -> int:
        """
        Count IR blocks persisted for a document.

        Args:
            session (AsyncSession): Active session.
            document_id (uuid.UUID): Owning document.

        Returns:
            int: Total block count (0 if parsing has not run yet).
        """
        return int(
            await session.scalar(
                select(func.count()).select_from(BlockModel).where(
                    BlockModel.document_id == document_id
                )
            ) or 0
        )

    async def get_stage_run_summary(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> dict[str, str]:
        """
        Return the best observed status per pipeline node for a document.

        When a node has been retried, the ranking ``done > running > pending > failed``
        is used so a later successful run supersedes an older failure.

        Args:
            session (AsyncSession): Active session.
            document_id (uuid.UUID): Owning document.

        Returns:
            dict[str, str]: ``{node_id: status}`` e.g. ``{"s0": "done", "s1": "done"}``.
        """
        result = await session.execute(
            select(StageRunModel.node_id, StageRunModel.status).where(
                StageRunModel.document_id == document_id
            )
        )
        _RANK = {"done": 4, "running": 3, "pending": 2, "failed": 1}
        summary: dict[str, str] = {}
        for node_id, status in result.all():
            if _RANK.get(status, 0) > _RANK.get(summary.get(node_id, ""), 0):
                summary[node_id] = status
        return summary

    async def list_by_collection(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[DocumentModel]:
        """
        Return a page of documents in a collection with optional filter and sort.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Parent collection.
            status_filter (str | None): Restrict to documents with this status.
            limit (int): Maximum number of rows to return.
            offset (int): Number of rows to skip (for pagination).
            sort_by (str): Column to sort by — one of ``created_at``, ``filename``,
                ``status``, ``file_size``.
            sort_order (str): ``"asc"`` or ``"desc"``.

        Returns:
            list[DocumentModel]: Documents matching the criteria.
        """
        _SORT_COLUMNS = {
            "created_at": DocumentModel.created_at,
            "filename": DocumentModel.filename,
            "status": DocumentModel.status,
            "file_size": DocumentModel.file_size,
        }
        col = _SORT_COLUMNS.get(sort_by, DocumentModel.created_at)
        order = col.desc() if sort_order == "desc" else col.asc()

        query = select(DocumentModel).where(DocumentModel.collection_id == collection_id)
        if status_filter is not None:
            query = query.where(DocumentModel.status == status_filter)
        query = query.order_by(order).limit(limit).offset(offset)

        result = await session.execute(query)
        return list(result.scalars().all())
