# ====== Code Summary ======
# DocumentMetadataApi — the data-access API for a document's metadata VALUES (document_metadata and
# the chunk-scope reads): the plain and named reads, the filterable / searchable selects that feed
# the Qdrant payload and named vectors, and the generated-set replace, partial upsert, clear and
# ``updated_at`` touch writes. Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, TextSanitizer

from ...tables import Chunk, ChunkMetadata, Document, DocumentMetadata, MetadataField


class DocumentMetadataApi:
    """Static data-access API for a document's metadata values."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentMetadataApi is a static-only class and cannot be instantiated.")

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

    @staticmethod
    async def touch(session: AsyncSession, document_id: uuid.UUID) -> None:
        """
        Bump a document's ``updated_at`` — a write that changed only its CHILD rows (metadata values).

        The ORM ``onupdate`` fires only when a document column changes; a value edit touches
        ``document_metadata`` alone, so without this the document would look unchanged to readers
        keyed on ``updated_at`` (e.g. the describe cache's collection change stamp).

        Args:
            session (AsyncSession): The unit of work (the same one that wrote the values).
            document_id (uuid.UUID): The document whose values changed.
        """
        # 1. Wall-clock time, not now() (the transaction START): a long write committing after a
        #    shorter one must still move the max(updated_at) change stamp.
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(updated_at=func.clock_timestamp())
        )

    @staticmethod
    async def update_metadata(
        session: AsyncSession, document_id: uuid.UUID, changes: Sequence[DocumentMetadata]
    ) -> None:
        """
        Partially upsert a document's metadata VALUES — only the listed fields, by (document, field).

        Unlike ``replace_metadata`` (which rewrites the whole GENERATED set on re-ingest), this
        touches ONLY the given fields: each row is inserted or, when a value already exists for that
        ``(document_id, field_id)``, its value+origin is overwritten in place — every other stored
        value is left untouched. This is the value-edit path (correct a single field without a
        re-ingest). Each value is NUL-stripped at this write boundary (Postgres rejects U+0000 in a
        text/jsonb value), mirroring the admission path.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose values are patched.
            changes (Sequence[DocumentMetadata]): The rows to upsert — each carries its ``field_id``,
                ``value`` and ``origin``; ``document_id`` is supplied here, not read from the row.
        """
        # 1. Nothing listed → nothing to write.
        if not changes:
            return
        # 2. One bulk upsert keyed on the unique (document_id, field_id): insert new rows, overwrite
        #    the value+origin of any that already exist. Each value is NUL-stripped for Postgres.
        rows = [
            {
                "document_id": document_id,
                "field_id": row.field_id,
                "value": TextSanitizer.strip_nul(row.value),
                "origin": row.origin,
            }
            for row in changes
        ]
        statement = pg_insert(DocumentMetadata).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["document_id", "field_id"],
            set_={"value": statement.excluded.value, "origin": statement.excluded.origin},
        )
        await session.execute(statement)

    @staticmethod
    async def delete_metadata(
        session: AsyncSession, document_id: uuid.UUID, field_ids: Sequence[int]
    ) -> None:
        """
        Delete a document's metadata rows for the given fields — the value-CLEAR path.

        The inverse of ``update_metadata``: clearing a field (``PATCH … metadata`` with a ``null``
        value) removes its stored value entirely rather than overwriting it. Only the listed
        ``(document_id, field_id)`` rows are deleted; every other stored value is left untouched.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose values are cleared.
            field_ids (Sequence[int]): The schema field ids whose rows are deleted.
        """
        # 1. Nothing listed → nothing to delete.
        if not field_ids:
            return
        # 2. Delete only the listed (document_id, field_id) rows.
        await session.execute(
            delete(DocumentMetadata).where(
                DocumentMetadata.document_id == document_id,
                DocumentMetadata.field_id.in_(field_ids),
            )
        )


__all__ = ["DocumentMetadataApi"]
