# ====== Code Summary ======
# StorageFootprintApi — the read-only, aggregate-in-SQL data access for a collection's material
# footprint in Postgres. It answers three questions without ever fetching rows into Python: how many
# EXACT S3 bytes each document references (from the content-addressed blob registry, deduped per
# document) and how many unique physical bytes the whole collection holds; and an ESTIMATE of the
# on-disk row bytes of the exploded IR, grouped per document AND per storage bucket via a single
# ``pg_column_size`` roll-up. Every query is a grouped aggregate — never a per-row scan.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The per-document, per-bucket on-disk row-byte estimate. Each SELECT tags its rows with the bucket
# the response exposes; ``pg_column_size(t.*)`` is the real in-tuple size of a row's columns (it
# excludes index, TOAST-external and page-bloat overhead — hence "estimated"). A single UNION ALL
# means ONE round trip for the whole collection, grouped server-side by (document, bucket).
_PG_PER_DOCUMENT_SQL = text(
    """
    SELECT document_id, bucket, SUM(bytes) AS bytes
    FROM (
        SELECT d.id AS document_id, 'documents' AS bucket, pg_column_size(d.*) AS bytes
        FROM document d
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT pa.document_id, 'documents', pg_column_size(pa.*)
        FROM page pa JOIN document d ON pa.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT bl.document_id, 'ir_blocks', pg_column_size(bl.*)
        FROM block bl JOIN document d ON bl.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT bl.document_id, 'ir_blocks', pg_column_size(bt.*)
        FROM block_table bt
        JOIN block bl ON bt.block_id = bl.id
        JOIN document d ON bl.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT bl.document_id, 'ir_blocks', pg_column_size(bf.*)
        FROM block_figure bf
        JOIN block bl ON bf.block_id = bl.id
        JOIN document d ON bl.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT bl.document_id, 'enrichment', pg_column_size(be.*)
        FROM block_enrichment be
        JOIN block bl ON be.block_id = bl.id
        JOIN document d ON bl.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT ch.document_id, 'chunks', pg_column_size(ch.*)
        FROM chunk ch JOIN document d ON ch.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT ch.document_id, 'chunks', pg_column_size(cb.*)
        FROM chunk_block cb
        JOIN chunk ch ON cb.chunk_id = ch.id
        JOIN document d ON ch.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT ch.document_id, 'chunks', pg_column_size(cm.*)
        FROM chunk_metadata cm
        JOIN chunk ch ON cm.chunk_id = ch.id
        JOIN document d ON ch.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT dm.document_id, 'metadata', pg_column_size(dm.*)
        FROM document_metadata dm
        JOIN document d ON dm.document_id = d.id
        WHERE d.collection_id = :cid
        UNION ALL
        SELECT j.document_id, 'observability', pg_column_size(j.*)
        FROM job j
        WHERE j.collection_id = :cid
        UNION ALL
        SELECT j.document_id, 'observability', pg_column_size(jse.*)
        FROM job_stage_event jse
        JOIN job j ON jse.job_id = j.id
        WHERE j.collection_id = :cid
    ) rollup
    GROUP BY document_id, bucket
    """
)

# The EXACT per-document S3 bytes: the four blob-referencing columns UNION-ed to their content hash
# (UNION, not UNION ALL, so a blob referenced twice by one document counts ONCE — content-addressed),
# joined to the registry for the byte size, then split original vs derived by blob kind.
_S3_PER_DOCUMENT_SQL = text(
    """
    WITH doc_blob AS (
        SELECT d.id AS document_id, d.source_hash AS content_hash
        FROM document d WHERE d.collection_id = :cid
        UNION
        SELECT d.id, d.pdf_blob_hash
        FROM document d WHERE d.collection_id = :cid AND d.pdf_blob_hash IS NOT NULL
        UNION
        SELECT pa.document_id, pa.render_blob_hash
        FROM page pa JOIN document d ON pa.document_id = d.id
        WHERE d.collection_id = :cid AND pa.render_blob_hash IS NOT NULL
        UNION
        SELECT bl.document_id, bf.crop_blob_hash
        FROM block_figure bf
        JOIN block bl ON bf.block_id = bl.id
        JOIN document d ON bl.document_id = d.id
        WHERE d.collection_id = :cid AND bf.crop_blob_hash IS NOT NULL
    )
    SELECT db.document_id,
           COALESCE(SUM(bl.size_bytes) FILTER (WHERE bl.kind = 'original'), 0) AS original_bytes,
           COALESCE(SUM(bl.size_bytes) FILTER (WHERE bl.kind <> 'original'), 0) AS rendered_bytes
    FROM doc_blob db JOIN blob bl ON bl.content_hash = db.content_hash
    GROUP BY db.document_id
    """
)

# The EXACT physical bytes the collection holds: every referenced content hash DEDUPED across all
# documents (UNION), summed once — so a blob shared by two documents (a re-uploaded file, a repeated
# logo) is counted a single time, the real disk cost.
_S3_PHYSICAL_UNIQUE_SQL = text(
    """
    WITH col_blob AS (
        SELECT d.source_hash AS content_hash
        FROM document d WHERE d.collection_id = :cid
        UNION
        SELECT d.pdf_blob_hash
        FROM document d WHERE d.collection_id = :cid AND d.pdf_blob_hash IS NOT NULL
        UNION
        SELECT pa.render_blob_hash
        FROM page pa JOIN document d ON pa.document_id = d.id
        WHERE d.collection_id = :cid AND pa.render_blob_hash IS NOT NULL
        UNION
        SELECT bf.crop_blob_hash
        FROM block_figure bf
        JOIN block bl ON bf.block_id = bl.id
        JOIN document d ON bl.document_id = d.id
        WHERE d.collection_id = :cid AND bf.crop_blob_hash IS NOT NULL
    )
    SELECT COALESCE(SUM(bl.size_bytes), 0)
    FROM col_blob cb JOIN blob bl ON bl.content_hash = cb.content_hash
    """
)

# The collection's documents (id + display name), so a document with zero rows/blobs still appears.
_DOCUMENT_NAMES_SQL = text("SELECT id, filename FROM document WHERE collection_id = :cid")

# Which documents populate which SEMANTIC metadata field — the carrier set of each ``meta_<slug>_dense``
# named vector. A document-scope value rides EVERY chunk point of the document (document_metadata); a
# chunk-scope value rides the chunks that carry it (chunk_metadata) — both surface the document here,
# and the facade weights the field's vector by that document's point count. Without this, a sparsely
# populated semantic field's dense vector would be (wrongly) charged to every point in the collection.
_SEMANTIC_FIELD_CARRIERS_SQL = text(
    """
    SELECT DISTINCT dm.document_id, mf.field_name
    FROM metadata_field mf
    JOIN document_metadata dm ON dm.field_id = mf.id
    JOIN document d ON dm.document_id = d.id
    WHERE mf.collection_id = :cid AND mf.semantic = true AND d.collection_id = :cid
    UNION
    SELECT DISTINCT ch.document_id, mf.field_name
    FROM metadata_field mf
    JOIN chunk_metadata cm ON cm.field_id = mf.id
    JOIN chunk ch ON cm.chunk_id = ch.id
    JOIN document d ON ch.document_id = d.id
    WHERE mf.collection_id = :cid AND mf.semantic = true AND d.collection_id = :cid
    """
)


class StorageFootprintApi:
    """Static, read-only aggregate queries for a collection's storage footprint (S3 + Postgres)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StorageFootprintApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def document_names(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str]]:
        """
        Return every document (id, filename) in the collection.

        Args:
            session (AsyncSession): The unit of work.
            collection_id (uuid.UUID): The collection to list.

        Returns:
            list[tuple[uuid.UUID, str]]: One (id, filename) pair per document.
        """
        result = await session.execute(_DOCUMENT_NAMES_SQL, {"cid": str(collection_id)})
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def per_document_pg(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[tuple[uuid.UUID | None, str, int]]:
        """
        Return the ESTIMATED on-disk row bytes per (document, storage bucket) in one grouped query.

        A ``None`` document id is possible for the ``observability`` bucket (a job may carry no
        document) — the caller folds those into the collection total but not into any document.

        Args:
            session (AsyncSession): The unit of work.
            collection_id (uuid.UUID): The collection to measure.

        Returns:
            list[tuple[uuid.UUID | None, str, int]]: (document_id, bucket, bytes) rows.
        """
        result = await session.execute(_PG_PER_DOCUMENT_SQL, {"cid": str(collection_id)})
        return [(row[0], row[1], int(row[2] or 0)) for row in result.all()]

    @staticmethod
    async def s3_per_document(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, int, int]]:
        """
        Return the EXACT (original, rendered) S3 bytes each document references (deduped per document).

        Args:
            session (AsyncSession): The unit of work.
            collection_id (uuid.UUID): The collection to measure.

        Returns:
            list[tuple[uuid.UUID, int, int]]: (document_id, original_bytes, rendered_bytes) rows.
        """
        result = await session.execute(_S3_PER_DOCUMENT_SQL, {"cid": str(collection_id)})
        return [(row[0], int(row[1] or 0), int(row[2] or 0)) for row in result.all()]

    @staticmethod
    async def s3_physical_unique(session: AsyncSession, collection_id: uuid.UUID) -> int:
        """
        Return the EXACT unique physical S3 bytes the collection holds (deduped across all documents).

        Args:
            session (AsyncSession): The unit of work.
            collection_id (uuid.UUID): The collection to measure.

        Returns:
            int: The summed size of every distinct referenced blob.
        """
        result = await session.execute(_S3_PHYSICAL_UNIQUE_SQL, {"cid": str(collection_id)})
        return int(result.scalar() or 0)

    @staticmethod
    async def semantic_field_carriers(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str]]:
        """
        Return (document_id, field_name) for every semantic field a document populates.

        The carrier set of each ``meta_<slug>_dense`` named vector: a semantic metadata dense vector
        rides only the points of documents that populate the field, so the caller weights the vector
        by these documents' point counts rather than the whole collection.

        Args:
            session (AsyncSession): The unit of work.
            collection_id (uuid.UUID): The collection to inspect.

        Returns:
            list[tuple[uuid.UUID, str]]: (document_id, field_name) pairs (empty with no semantic fields).
        """
        result = await session.execute(_SEMANTIC_FIELD_CARRIERS_SQL, {"cid": str(collection_id)})
        return [(row[0], row[1]) for row in result.all()]


__all__ = ["StorageFootprintApi"]
