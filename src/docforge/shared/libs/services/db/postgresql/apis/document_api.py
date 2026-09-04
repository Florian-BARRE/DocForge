# ====== Code Summary ======
# DocumentApi — the data-access API for the document domain: the catalogue record, its metadata
# VALUES (document_metadata) and its pages. Includes the dedup lookup (collection + source_hash +
# pipeline_version) and the status transitions the ingestion job drives. Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope

from ..tables import (
    Chunk,
    ChunkMetadata,
    Document,
    DocumentMetadata,
    DocumentStatus,
    MetadataField,
    Page,
    SourceKind,
)


class DocumentApi:
    """Static data-access API for the document, its metadata values and its pages."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentApi is a static-only class and cannot be instantiated.")

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
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[Document]:
        """Return the documents of a collection, newest first."""
        result = await session.execute(
            select(Document)
            .where(Document.collection_id == collection_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

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
    async def finalize_done(session: AsyncSession, document_id: uuid.UUID) -> None:
        """
        Mark a document DONE at the end of a successful run — UNLESS it was CANCELLED meanwhile.

        A force-cancel can commit CANCELLED in the sub-second window while the persist tail runs;
        guarding the terminal DONE write keeps a force-cancelled document from flipping back to DONE
        (mirrors the ``JobApi.mark_done`` CANCELLED guard on the job side).
        """
        document = await session.get(Document, document_id)
        if document is not None and document.status != DocumentStatus.CANCELLED:
            document.status = DocumentStatus.DONE

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

    # -------------------- metadata values --------------------
    @staticmethod
    async def get_metadata(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentMetadata]:
        """Return the document's metadata values."""
        result = await session.execute(
            select(DocumentMetadata).where(DocumentMetadata.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_metadata_with_names(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[tuple[str, Any, FieldOrigin]]:
        """
        Return (field_name, value, origin) for every metadata value of a document — the export shape.

        The field NAME travels instead of the autoincrement ``field_id`` so a bundle stays portable:
        the importer re-resolves the value to the freshly-minted field id by name (the integer key
        is re-assigned on the target server).
        """
        result = await session.execute(
            select(MetadataField.field_name, DocumentMetadata.value, DocumentMetadata.origin)
            .join(MetadataField, MetadataField.id == DocumentMetadata.field_id)
            .where(DocumentMetadata.document_id == document_id)
        )
        return [(name, value, origin) for name, value, origin in result.all()]

    @staticmethod
    async def get_metadata_for_documents(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[DocumentMetadata]]:
        """
        Bulk-load EVERY document-metadata value for a page of documents — one query, no N+1.

        The grid renders a compact ``{field_name: value}`` map per row; resolving the field names
        (against the collection schema) is the caller's job, so this returns the raw value rows
        grouped by document. A document with no metadata is simply absent from the map.

        Args:
            session (AsyncSession): The unit of work.
            document_ids (Sequence[uuid.UUID]): The page's documents (bounded by the page size).

        Returns:
            dict[uuid.UUID, list[DocumentMetadata]]: document id → its metadata value rows.
        """
        if not document_ids:
            return {}
        result = await session.execute(
            select(DocumentMetadata).where(DocumentMetadata.document_id.in_(document_ids))
        )
        grouped: dict[uuid.UUID, list[DocumentMetadata]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.document_id, []).append(row)
        return grouped

    @staticmethod
    async def get_filterable_metadata(
        session: AsyncSession, document_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Return a document's FILTERABLE document-scope metadata as ``{field_name: decoded value}``.

        Joins each value to its schema field and keeps only the fields declared ``filterable`` and
        ``document``-scoped (any origin — user- and generated-supplied alike). This is exactly the
        set that must be denormalised onto every chunk's Qdrant payload to become a search filter.
        The JSONB value comes back already decoded by the driver, so the plain Python value (string,
        number or list) is what lands on the payload.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose filterable metadata is read.

        Returns:
            dict[str, Any]: Field name → its decoded document-scope value.
        """
        result = await session.execute(
            select(MetadataField.field_name, DocumentMetadata.value)
            .join(MetadataField, MetadataField.id == DocumentMetadata.field_id)
            .where(
                DocumentMetadata.document_id == document_id,
                MetadataField.filterable.is_(True),
                MetadataField.scope == FieldScope.DOCUMENT,
            )
        )
        return {name: value for name, value in result.all()}

    @staticmethod
    async def get_filterable_metadata_for_documents(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, Any]]:
        """
        Bulk variant of ``get_filterable_metadata`` — one query for a set of documents.

        The search hydration path resolves a hit page (a handful of distinct documents) to their
        filterable document-scope metadata in a SINGLE round-trip, so a self-citing hit needs no
        per-document N+1.

        Args:
            session (AsyncSession): The unit of work.
            document_ids (Sequence[uuid.UUID]): The documents whose filterable metadata is read.

        Returns:
            dict[uuid.UUID, dict[str, Any]]: document id → {field name → decoded value} (a document
                with no filterable metadata is simply absent from the map).
        """
        if not document_ids:
            return {}
        result = await session.execute(
            select(DocumentMetadata.document_id, MetadataField.field_name, DocumentMetadata.value)
            .join(MetadataField, MetadataField.id == DocumentMetadata.field_id)
            .where(
                DocumentMetadata.document_id.in_(document_ids),
                MetadataField.filterable.is_(True),
                MetadataField.scope == FieldScope.DOCUMENT,
            )
        )
        out: dict[uuid.UUID, dict[str, Any]] = {}
        for document_id, name, value in result.all():
            out.setdefault(document_id, {})[name] = value
        return out

    @staticmethod
    async def get_chunk_filterable_metadata(
        session: AsyncSession, document_id: uuid.UUID
    ) -> dict[uuid.UUID, dict[str, Any]]:
        """
        Return a document's FILTERABLE CHUNK-scope metadata as ``{chunk_id: {field_name: value}}``.

        The chunk-scope sibling of ``get_filterable_metadata``: chunk-scope values live one-per-chunk
        in ``chunk_metadata``, so each chunk carries its OWN filterable values (unlike a document-scope
        value that is uniform across the document). This is exactly what a backfill must denormalise
        onto each individual chunk point when a chunk-scope field is toggled filterable after ingest —
        the ingest write path already does it inline, this repairs points created before the toggle.
        Only ``filterable`` + ``chunk``-scoped fields (any origin) are returned.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose chunk-scope filterable metadata is read.

        Returns:
            dict[uuid.UUID, dict[str, Any]]: chunk id → {field name → decoded value} (a chunk with no
                filterable chunk-scope metadata is simply absent from the map).
        """
        result = await session.execute(
            select(ChunkMetadata.chunk_id, MetadataField.field_name, ChunkMetadata.value)
            .join(MetadataField, MetadataField.id == ChunkMetadata.field_id)
            .join(Chunk, Chunk.id == ChunkMetadata.chunk_id)
            .where(
                Chunk.document_id == document_id,
                MetadataField.filterable.is_(True),
                MetadataField.scope == FieldScope.CHUNK,
            )
        )
        out: dict[uuid.UUID, dict[str, Any]] = {}
        for chunk_id, name, value in result.all():
            out.setdefault(chunk_id, {})[name] = value
        return out

    @staticmethod
    async def get_searchable_metadata(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[tuple[str, Any, bool, bool]]:
        """
        Return a document's SEMANTIC-or-LEXICAL document-scope metadata with its per-field flags.

        Joins each value to its schema field and keeps only the document-scoped fields flagged
        ``semantic`` and/or ``lexical`` (any origin). This is exactly the set whose values must be
        embedded into the ``meta_<slug>_dense`` / ``meta_<slug>_bm25`` named vectors on every chunk
        point of the document, so document-level metadata becomes semantically/lexically searchable.
        The flags travel with each row so the caller knows which vector(s) a value feeds.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose searchable metadata is read.

        Returns:
            list[tuple[str, Any, bool, bool]]: (field name, decoded value, semantic, lexical) rows.
        """
        result = await session.execute(
            select(
                MetadataField.field_name,
                DocumentMetadata.value,
                MetadataField.semantic,
                MetadataField.lexical,
            )
            .join(MetadataField, MetadataField.id == DocumentMetadata.field_id)
            .where(
                DocumentMetadata.document_id == document_id,
                MetadataField.scope == FieldScope.DOCUMENT,
                or_(MetadataField.semantic.is_(True), MetadataField.lexical.is_(True)),
            )
        )
        return [(name, value, semantic, lexical) for name, value, semantic, lexical in result.all()]

    @staticmethod
    async def replace_metadata(
        session: AsyncSession, document_id: uuid.UUID, values: list[DocumentMetadata]
    ) -> None:
        """
        Replace the document's GENERATED metadata values with ``values``.

        USER-declared rows are written once at admission and must SURVIVE re-ingestion —
        a run's payload only carries generated values, so a blanket delete would wipe the
        declared metadata (and the next re-admission would then reject the document for a
        missing required field — caught in the first real e2e run).
        """
        await session.execute(
            delete(DocumentMetadata).where(
                DocumentMetadata.document_id == document_id,
                DocumentMetadata.origin == FieldOrigin.GENERATED,
            )
        )
        session.add_all(values)

    # -------------------- pages --------------------
    @staticmethod
    async def replace_pages(
        session: AsyncSession, document_id: uuid.UUID, pages: list[Page]
    ) -> None:
        """Replace a document's pages (idempotent on re-ingest)."""
        await session.execute(delete(Page).where(Page.document_id == document_id))
        session.add_all(pages)

    @staticmethod
    async def get_pages(session: AsyncSession, document_id: uuid.UUID) -> list[Page]:
        """Return a document's pages, in order."""
        result = await session.execute(
            select(Page).where(Page.document_id == document_id).order_by(Page.page_number)
        )
        return list(result.scalars().all())


__all__ = ["DocumentApi"]
