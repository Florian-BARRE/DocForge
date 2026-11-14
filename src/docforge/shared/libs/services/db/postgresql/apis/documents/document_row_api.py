# ====== Code Summary ======
# DocumentRowApi — the data-access API for the core document row: create / get / dedup lookup,
# collection listings and counts, the ingestion status transitions the job drives, the searchability
# toggle, the facts the pipeline learns, and single / bulk delete. Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import Document, DocumentStatus, SourceKind


class DocumentRowApi:
    """Static data-access API for the core document rows (catalogue record and its status)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentRowApi is a static-only class and cannot be instantiated.")

    # -------------------- document --------------------
    @staticmethod
    async def create(session: AsyncSession, document: Document) -> Document:
        """Insert a document and return it (flushed)."""
        session.add(document)
        await session.flush()
        return document

    @staticmethod
    async def get(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
        """Fetch a document by id, or None."""
        return await session.get(Document, document_id)

    @staticmethod
    async def get_for_update(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
        """
        Fetch a document by id, locking its row ``FOR UPDATE`` — or None.

        Serialises concurrent reingest admissions of the SAME document: the second admission blocks
        on the row lock until the first commits, then sees its freshly-minted PENDING job and refuses
        (rather than both passing the active-job check and minting two parallel runs). A lightweight
        single-row lock, held only for the admission transaction.
        """
        return await session.get(Document, document_id, with_for_update=True)

    @staticmethod
    async def get_by_ids(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> list[Document]:
        """Fetch documents by id — used to resolve a set of chunks back to their collections."""
        if not document_ids:
            return []
        result = await session.execute(select(Document).where(Document.id.in_(document_ids)))
        return list(result.scalars().all())

    @staticmethod
    async def find(
        session: AsyncSession, collection_id: uuid.UUID, source_hash: str, pipeline_version: str
    ) -> Document | None:
        """Dedup lookup: the document with this (collection, source_hash, pipeline_version), or None."""
        result = await session.execute(
            select(Document).where(
                Document.collection_id == collection_id,
                Document.source_hash == source_hash,
                Document.pipeline_version == pipeline_version,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_collection(
        session: AsyncSession,
        collection_id: uuid.UUID,
        status: DocumentStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Document]:
        """
        Return the documents of a collection, newest first — optionally status-filtered and paged.

        The order is id-stabilised (``created_at`` desc, then ``id`` desc) so offset paging never
        skips or duplicates a row when several documents share a creation timestamp.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The owning collection.
            status (DocumentStatus | None): Keep only documents in this status (None = every status).
            limit (int | None): Cap the rows returned (None = unbounded, the full-list callers' need).
            offset (int): Rows to skip for paging (0 = the first page).

        Returns:
            list[Document]: The matching documents, newest first (at most ``limit`` when set).
        """
        conditions = [Document.collection_id == collection_id]
        if status is not None:
            conditions.append(Document.status == status)
        statement = (
            select(Document)
            .where(*conditions)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        result = await session.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def count_for_collection(
        session: AsyncSession,
        collection_id: uuid.UUID,
        status: DocumentStatus | None = None,
    ) -> int:
        """
        Count a collection's documents (optionally status-filtered) — the estimate's true scope size.

        Lets the cost estimate learn how many documents its whole-collection scope covers WITHOUT
        loading them, so it can measure only a bounded sample and scale the projection linearly.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection to count.
            status (DocumentStatus | None): Count only this status (None = every status).

        Returns:
            int: The number of matching documents (0 when none).
        """
        conditions = [Document.collection_id == collection_id]
        if status is not None:
            conditions.append(Document.status == status)
        result = await session.execute(
            select(func.count()).select_from(Document).where(*conditions)
        )
        return int(result.scalar_one())

    @staticmethod
    async def count_by_collections(
        session: AsyncSession, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """
        Return the document count of each collection in ONE grouped query (no per-collection N+1).

        The fleet-dashboard doc-count for every collection at once — a collection with no documents
        is simply absent from the result map (the caller defaults it to 0), never a missing row error.

        Args:
            session (AsyncSession): The active session.
            collection_ids (Sequence[uuid.UUID]): The collections to count (empty → empty map).

        Returns:
            dict[uuid.UUID, int]: collection id → its document count (collections with 0 omitted).
        """
        # 1. Nothing to count — skip the round-trip entirely.
        if not collection_ids:
            return {}
        # 2. One GROUP BY over the scoped set — the whole fleet's counts in a single index scan.
        result = await session.execute(
            select(Document.collection_id, func.count())
            .where(Document.collection_id.in_(collection_ids))
            .group_by(Document.collection_id)
        )
        return {collection_id: count for collection_id, count in result.all()}

    @staticmethod
    async def set_status(
        session: AsyncSession, document_id: uuid.UUID, status: DocumentStatus
    ) -> None:
        """Update a document's ingestion status."""
        document = await session.get(Document, document_id)
        if document is not None:
            document.status = status

    @staticmethod
    async def finalize_done(
        session: AsyncSession,
        document_id: uuid.UUID,
        *,
        warning_reason: str | None = None,
        chunk_count: int | None = None,
    ) -> None:
        """
        Mark a document DONE at the end of a successful run — UNLESS it was CANCELLED meanwhile.

        A force-cancel can commit CANCELLED in the sub-second window while the persist tail runs;
        guarding the terminal DONE write keeps a force-cancelled document from flipping back to DONE
        (mirrors the ``JobApi.mark_done`` CANCELLED guard on the job side).

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document to finalize.
            warning_reason (str | None): A non-fatal, human-readable warning to surface on the DONE
                document (e.g. a 0-chunk run that produced nothing retrievable). None clears it — a
                normal run with chunks passes None so a re-ingest wipes a stale warning.
            chunk_count (int | None): The number of chunks persisted for the document (0 for the
                empty case). Denormalized so the grid/overview need no COUNT. None leaves it unchanged.
        """
        document = await session.get(Document, document_id)
        if document is not None and document.status != DocumentStatus.CANCELLED:
            document.status = DocumentStatus.DONE
            document.warning_reason = warning_reason
            if chunk_count is not None:
                document.chunk_count = chunk_count

    @staticmethod
    async def flag_replay_failure(
        session: AsyncSession, document_id: uuid.UUID, warning_reason: str
    ) -> None:
        """
        Stamp a failed replay's warning, keeping a DONE/FAILED status (else fall back to FAILED).

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The replayed document.
            warning_reason (str): The failure surfaced on the document.
        """
        document = await session.get(Document, document_id)
        if document is None:
            return
        if document.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
            document.status = DocumentStatus.FAILED
        document.warning_reason = warning_reason

    @staticmethod
    async def mark_processing(session: AsyncSession, document_id: uuid.UUID) -> None:
        """
        Transition a document PENDING → PROCESSING at job-claim time.

        Guarded to the PENDING → PROCESSING edge only: a document already DONE/FAILED (or already
        PROCESSING) is left untouched, so a late claim or a race can never clobber a terminal state
        with PROCESSING. A re-ingest resets the row to PENDING first, so it is eligible again.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose ingestion is starting.
        """
        document = await session.get(Document, document_id)
        if document is not None and document.status == DocumentStatus.PENDING:
            document.status = DocumentStatus.PROCESSING

    @staticmethod
    async def set_enabled(session: AsyncSession, document_id: uuid.UUID, enabled: bool) -> bool:
        """
        Flip a document's searchability toggle (the reversible enable/disable flag).

        A pure Postgres flip — search reads this flag to exclude a disabled document's chunks,
        so no Qdrant point ever has to be touched (no per-chunk fan-out on a doc-level toggle).

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document to toggle.
            enabled (bool): The new searchability state.

        Returns:
            bool: Whether the document existed (False → the router raises a 404).
        """
        document = await session.get(Document, document_id)
        if document is None:
            return False
        document.enabled = enabled
        return True

    @staticmethod
    async def set_enabled_many(
        session: AsyncSession, document_ids: Sequence[uuid.UUID], enabled: bool
    ) -> int:
        """
        Bulk-flip the searchability toggle of a set of documents in ONE statement.

        The document-level toggle is pure Postgres (search reads the flag via a bounded ``must_not``
        exclusion), so a mass enable/disable never fans out to Qdrant. Returns the number of rows
        actually changed so the caller can report ``updated`` distinctly from ``matched``.

        Args:
            session (AsyncSession): The unit of work.
            document_ids (Sequence[uuid.UUID]): The documents to toggle.
            enabled (bool): The new searchability state.

        Returns:
            int: How many rows were updated (0 when the set is empty).
        """
        if not document_ids:
            return 0
        result = await session.execute(
            update(Document)
            .where(Document.id.in_(document_ids), Document.enabled.is_(not enabled))
            .values(enabled=enabled)
        )
        return int(result.rowcount or 0)

    @staticmethod
    async def list_disabled_ids(
        session: AsyncSession, collection_id: uuid.UUID, limit: int | None = None
    ) -> list[uuid.UUID]:
        """
        Return the ids of a collection's DISABLED documents — the search exclusion set.

        Bounded by the document count of one collection (not chunks), so the resulting
        ``must_not document_id in {...}`` Qdrant clause stays a single cheap membership filter.

        Args:
            session (AsyncSession): The open read session.
            collection_id (uuid.UUID): The collection to scope to.
            limit (int | None): Optional row cap — the search facade reads ``cap + 1`` to detect an
                over-cap exclusion set without loading it whole (then it flips to a positive filter).
        """
        statement = select(Document.id).where(
            Document.collection_id == collection_id, Document.enabled.is_(False)
        )
        if limit is not None:
            statement = statement.limit(limit)
        result = await session.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def list_enabled_ids(session: AsyncSession, collection_id: uuid.UUID) -> list[uuid.UUID]:
        """
        Return the ids of a collection's ENABLED documents — the positive search-scope fallback.

        Used only when the disabled set exceeds the exclusion cap: on a mostly-archived collection the
        enabled set is the smaller one, so scoping search to ``document_id in {enabled}`` keeps the
        per-query Qdrant filter bounded by it instead of by the huge disabled ``must_not``.
        """
        result = await session.execute(
            select(Document.id).where(
                Document.collection_id == collection_id, Document.enabled.is_(True)
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_facts(
        session: AsyncSession,
        document_id: uuid.UUID,
        *,
        title: str | None = None,
        language: str | None = None,
        page_count: int | None = None,
        source_kind: SourceKind | None = None,
        pdf_blob_hash: str | None = None,
        simhash: str | None = None,
    ) -> None:
        """
        Patch the facts the pipeline LEARNS about a document (None means 'leave unchanged').

        The row is created at admission with only the upload facts; parse/probe later fill the
        title, language, page count, refined source kind, PDF view and near-dup signature.
        """
        document = await session.get(Document, document_id)
        if document is None:
            return
        if title is not None:
            document.title = title
        if language is not None:
            document.language = language
        if page_count is not None:
            document.page_count = page_count
        if source_kind is not None:
            document.source_kind = source_kind
        if pdf_blob_hash is not None:
            document.pdf_blob_hash = pdf_blob_hash
        if simhash is not None:
            document.simhash = simhash

    @staticmethod
    async def delete(session: AsyncSession, document_id: uuid.UUID) -> bool:
        """Delete a document (cascading its blocks, chunks, metadata, pages, jobs); return existence."""
        document = await session.get(Document, document_id)
        if document is None:
            return False
        await session.delete(document)
        return True

    @staticmethod
    async def delete_many(session: AsyncSession, document_ids: Sequence[uuid.UUID]) -> int:
        """
        Set-based bulk delete — ``DELETE FROM document WHERE id IN (:ids)`` in ONE statement.

        The child rows (blocks, chunks, metadata, pages, jobs) fall away through the DB-level
        ``ON DELETE CASCADE`` on their ``document_id`` foreign keys — the same mechanism the
        single-row ``delete`` relies on (there are no ORM relationships), so a bulk delete is
        coherent without a per-row round-trip. The caller feeds this BOUNDED chunks.

        Args:
            session (AsyncSession): The unit of work.
            document_ids (Sequence[uuid.UUID]): The documents to delete (one bounded batch).

        Returns:
            int: How many document rows were actually removed.
        """
        if not document_ids:
            return 0
        result = await session.execute(delete(Document).where(Document.id.in_(document_ids)))
        return int(result.rowcount or 0)


__all__ = ["DocumentRowApi"]
