# ====== Code Summary ======
# BlobApi — the data-access API for the content-addressed blob registry. `register` is idempotent
# (same content hash → one row). Because blobs are content-addressed they may be SHARED across
# documents; deletion therefore goes through `delete_unreferenced` — the multi-reference safety
# purge: given candidate hashes, it removes ONLY the rows nothing references anymore (re-checked at
# delete time against document.source_hash, document.pdf_blob_hash, page.render_blob_hash and
# block_figure.crop_blob_hash) and RETURNS exactly the removed hashes, so only those get their S3
# object deleted — a concurrent ingest re-referencing a hash between snapshot and commit can never
# strand it.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import Blob, Block, BlockFigure, Document, Page


class BlobApi:
    """Static data-access API for the blob registry (content-addressed, reference-safe deletion)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BlobApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def register(session: AsyncSession, blob: Blob) -> Blob:
        """Insert the blob if its content hash is new, else return the existing row (idempotent)."""
        existing = await session.get(Blob, blob.content_hash)
        if existing is not None:
            return existing
        session.add(blob)
        await session.flush()
        return blob

    @staticmethod
    async def register_many(session: AsyncSession, blobs: Sequence[Blob]) -> None:
        """Register many blobs in ONE insert (idempotent per content hash) — the ingest path
        registers original/PDF/renders/crops per document; a per-row round-trip is wasteful."""
        if not blobs:
            return
        rows = [
            {
                "content_hash": blob.content_hash,
                "s3_key": blob.s3_key,
                "mime_type": blob.mime_type,
                "size_bytes": blob.size_bytes,
                "kind": blob.kind,
            }
            for blob in blobs
        ]
        statement = (
            pg_insert(Blob).values(rows).on_conflict_do_nothing(index_elements=["content_hash"])
        )
        await session.execute(statement)

    @staticmethod
    async def get(session: AsyncSession, content_hash: str) -> Blob | None:
        """Fetch a blob by its content hash, or None."""
        return await session.get(Blob, content_hash)

    @staticmethod
    async def get_many(session: AsyncSession, content_hashes: Sequence[str]) -> list[Blob]:
        """Fetch registry rows for a set of content hashes (the export blob-manifest read)."""
        if not content_hashes:
            return []
        result = await session.execute(
            select(Blob).where(Blob.content_hash.in_(list(content_hashes)))
        )
        return list(result.scalars().all())

    @staticmethod
    async def collections_for_hash(session: AsyncSession, content_hash: str) -> list[uuid.UUID]:
        """
        Return every collection whose documents reference this content-addressed blob.

        A blob is content-addressed and may be shared across documents (hence collections), so it
        has no single owner. This resolves the full owning set from the four referencing columns
        (document source + PDF, page render, figure crop) — the authorization gate uses it to let a
        scoped API key reach a blob only through a collection it is scoped to.

        Args:
            session (AsyncSession): The unit of work.
            content_hash (str): The blob's content hash.

        Returns:
            list[uuid.UUID]: The distinct collection ids referencing the blob (empty when orphan).
        """
        # 1. Documents referencing the blob directly (original bytes or canonical PDF).
        collections: set[uuid.UUID] = set()
        direct = await session.execute(
            select(Document.collection_id).where(
                or_(
                    Document.source_hash == content_hash,
                    Document.pdf_blob_hash == content_hash,
                )
            )
        )
        collections.update(direct.scalars())
        # 2. Documents referencing it as a page render.
        pages = await session.execute(
            select(Document.collection_id)
            .join(Page, Page.document_id == Document.id)
            .where(Page.render_blob_hash == content_hash)
        )
        collections.update(pages.scalars())
        # 3. Documents referencing it as a figure crop.
        figures = await session.execute(
            select(Document.collection_id)
            .join(Block, Block.document_id == Document.id)
            .join(BlockFigure, BlockFigure.block_id == Block.id)
            .where(BlockFigure.crop_blob_hash == content_hash)
        )
        collections.update(figures.scalars())
        return list(collections)

    @staticmethod
    async def collect_hashes_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[str]:
        """Gather every blob hash a document uses — the purge candidates before deleting it."""
        hashes: set[str] = set()
        # 1. The document's own blobs (original + canonical PDF).
        document = await session.get(Document, document_id)
        if document is not None:
            hashes.add(document.source_hash)
            if document.pdf_blob_hash is not None:
                hashes.add(document.pdf_blob_hash)
        # 2. Its page renders and figure crops.
        pages = await session.execute(
            select(Page.render_blob_hash).where(Page.document_id == document_id)
        )
        figures = await session.execute(
            select(BlockFigure.crop_blob_hash)
            .join(Block, BlockFigure.block_id == Block.id)
            .where(Block.document_id == document_id)
        )
        hashes.update(h for h in pages.scalars() if h is not None)
        hashes.update(h for h in figures.scalars() if h is not None)
        return list(hashes)

    @staticmethod
    async def collect_hashes_for_documents(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> list[str]:
        """
        Gather every blob hash a SET of documents uses — the batched purge-candidate collector.

        The set-based sibling of ``collect_hashes_for_document``: three ``IN``-scoped queries for a
        whole batch of documents (own blobs, page renders, figure crops) instead of ~3 per document,
        so a mass delete stays a handful of round-trips per batch rather than O(N).

        Args:
            session (AsyncSession): The unit of work.
            document_ids (Sequence[uuid.UUID]): The documents whose blob hashes are collected.

        Returns:
            list[str]: The distinct candidate hashes (feed to ``delete_unreferenced`` after the delete).
        """
        if not document_ids:
            return []
        hashes: set[str] = set()
        # 1. Every document's own blobs (original + canonical PDF).
        documents = await session.execute(
            select(Document.source_hash, Document.pdf_blob_hash).where(
                Document.id.in_(document_ids)
            )
        )
        for source_hash, pdf_hash in documents.all():
            hashes.add(source_hash)
            if pdf_hash is not None:
                hashes.add(pdf_hash)
        # 2. Every page render and figure crop across the batch.
        pages = await session.execute(
            select(Page.render_blob_hash).where(Page.document_id.in_(document_ids))
        )
        figures = await session.execute(
            select(BlockFigure.crop_blob_hash)
            .join(Block, BlockFigure.block_id == Block.id)
            .where(Block.document_id.in_(document_ids))
        )
        hashes.update(h for h in pages.scalars() if h is not None)
        hashes.update(h for h in figures.scalars() if h is not None)
        return list(hashes)

    @staticmethod
    async def collect_hashes_for_collection(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[str]:
        """Gather every blob hash a collection's documents use — purge candidates before delete."""
        hashes: set[str] = set()
        # 1. Every document's own blobs.
        documents = await session.execute(
            select(Document.source_hash, Document.pdf_blob_hash).where(
                Document.collection_id == collection_id
            )
        )
        for source_hash, pdf_hash in documents.all():
            hashes.add(source_hash)
            if pdf_hash is not None:
                hashes.add(pdf_hash)
        # 2. Every page render and figure crop, scoped by the collection.
        pages = await session.execute(
            select(Page.render_blob_hash)
            .join(Document, Page.document_id == Document.id)
            .where(Document.collection_id == collection_id)
        )
        figures = await session.execute(
            select(BlockFigure.crop_blob_hash)
            .join(Block, BlockFigure.block_id == Block.id)
            .join(Document, Block.document_id == Document.id)
            .where(Document.collection_id == collection_id)
        )
        hashes.update(h for h in pages.scalars() if h is not None)
        hashes.update(h for h in figures.scalars() if h is not None)
        return list(hashes)

    @staticmethod
    async def delete_unreferenced(
        session: AsyncSession, candidate_hashes: Sequence[str]
    ) -> list[str]:
        """
        Delete the registry rows for candidate hashes NOTHING references anymore — re-checked at
        delete time — and RETURN exactly the hashes removed (so only those get their S3 object purged).

        The concurrency-safe successor to a ``find_unreferenced`` SELECT followed by a ``delete_rows``
        DELETE. Those were two statements: the SELECT took its snapshot, and the DELETE (and the S3
        purge that followed the commit) ran later — a window in which a concurrent ingest of the SAME
        bytes (content-addressed dedup does an S3 put, then registers its reference rows) could
        reference a "candidate" hash AFTER the snapshot but before the commit. The deleter then judged
        it unreferenced and deleted its S3 object out from under the freshly-ingested document (which
        would 404 on read). Folding the reference test INTO the DELETE (``WHERE NOT EXISTS(reference)``)
        re-evaluates it against the DELETE's own snapshot, so a hash re-referenced by a committed
        concurrent ingest is left intact; ``RETURNING`` yields only the rows actually removed — the
        exact, race-free set to delete from S3.

        Args:
            session (AsyncSession): The unit of work (the caller commits, then S3-deletes the result).
            candidate_hashes (Sequence[str]): Hashes the deleted entity was using.

        Returns:
            list[str]: The hashes whose rows were actually removed (safe to delete from S3).
        """
        if not candidate_hashes:
            return []
        # A single guarded DELETE: drop each candidate row UNLESS any of the four referencing columns
        # still points at it (re-checked here, not at an earlier SELECT), and return what was removed.
        statement = (
            delete(Blob)
            .where(
                Blob.content_hash.in_(set(candidate_hashes)),
                ~exists().where(Document.source_hash == Blob.content_hash),
                ~exists().where(Document.pdf_blob_hash == Blob.content_hash),
                ~exists().where(Page.render_blob_hash == Blob.content_hash),
                ~exists().where(BlockFigure.crop_blob_hash == Blob.content_hash),
            )
            .returning(Blob.content_hash)
        )
        result = await session.execute(statement)
        return list(result.scalars().all())


__all__ = ["BlobApi"]
