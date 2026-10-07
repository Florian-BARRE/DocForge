# ====== Code Summary ======
# CollectionApi — the data-access API for the collection domain: the collection itself, its metadata
# SCHEMA (metadata_field), and its config history (config_version). Every method runs in a
# caller-supplied session so the Database façade can compose several apis in one transaction. It
# touches only Postgres; coherence with Qdrant/S3 is the façade's concern.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import Collection, ConfigVersion, Document, MetadataField


class CollectionApi:
    """Static data-access API for the collection, its schema and its config history."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionApi is a static-only class and cannot be instantiated.")

    # -------------------- collection --------------------
    @staticmethod
    async def create(session: AsyncSession, collection: Collection) -> Collection:
        """Insert a collection and return it (flushed, so its id is populated)."""
        session.add(collection)
        await session.flush()
        return collection

    @staticmethod
    async def get(session: AsyncSession, collection_id: uuid.UUID) -> Collection | None:
        """Fetch a collection by id, or None."""
        return await session.get(Collection, collection_id)

    @staticmethod
    async def get_for_update(session: AsyncSession, collection_id: uuid.UUID) -> Collection | None:
        """Fetch a collection by id under a ``FOR UPDATE`` row lock, or None.

        Serializes concurrent config-version minting: a second transaction that tries to lock the same
        collection blocks until the first commits, so the ``max(version) + 1`` read-modify-write can't
        interleave into a duplicate (collection_id, version). The lock is held until the caller's
        transaction ends.

        Args:
            session (AsyncSession): The unit of work the lock is scoped to.
            collection_id (uuid.UUID): The collection whose row is locked.

        Returns:
            Collection | None: The locked row, or None when the collection does not exist.
        """
        result = await session.execute(
            select(Collection).where(Collection.id == collection_id).with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(session: AsyncSession, name: str) -> Collection | None:
        """Fetch a collection by its unique name, or None."""
        result = await session.execute(select(Collection).where(Collection.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(session: AsyncSession) -> list[Collection]:
        """Return every collection."""
        result = await session.execute(select(Collection).order_by(Collection.name))
        return list(result.scalars().all())

    @staticmethod
    async def update(
        session: AsyncSession,
        collection_id: uuid.UUID,
        *,
        name: str | None = None,
        supported_formats: list[str] | None = None,
        tags: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        job_timeout_seconds: float | None = None,
        trace_verbosity: str | None = None,
        pipeline: dict | None = None,
        search: dict | None = None,
        needs_reindex: bool | None = None,
        indexed_signature: str | None = None,
        indexed_embed_signature: str | None = None,
    ) -> None:
        """Patch the provided contract fields on a collection (None means 'leave unchanged').

        ``tags`` follows the same convention: None leaves the current labels untouched, while an
        explicit empty list clears them back to untagged.
        """
        collection = await session.get(Collection, collection_id)
        if collection is None:
            return
        if name is not None:
            collection.name = name
        if supported_formats is not None:
            collection.supported_formats = supported_formats
        if tags is not None:
            collection.tags = tags
        if max_file_size_bytes is not None:
            collection.max_file_size_bytes = max_file_size_bytes
        if job_timeout_seconds is not None:
            collection.job_timeout_seconds = job_timeout_seconds
        if trace_verbosity is not None:
            collection.trace_verbosity = trace_verbosity
        if pipeline is not None:
            collection.pipeline = pipeline
        if search is not None:
            collection.search = search
        if needs_reindex is not None:
            collection.needs_reindex = needs_reindex
        if indexed_signature is not None:
            collection.indexed_signature = indexed_signature
        if indexed_embed_signature is not None:
            collection.indexed_embed_signature = indexed_embed_signature

    @staticmethod
    async def set_estimate_overrides(
        session: AsyncSession, collection_id: uuid.UUID, overrides: dict | None
    ) -> None:
        """Replace the collection's cost-estimate overrides (None clears them → global defaults).

        Distinct from ``update`` (whose None means 'leave unchanged'): this ALWAYS writes, so a caller
        can explicitly clear the overrides back to the defaults by passing None.
        """
        collection = await session.get(Collection, collection_id)
        if collection is None:
            return
        collection.estimate_overrides = overrides

    @staticmethod
    async def touch(session: AsyncSession, collection_id: uuid.UUID) -> None:
        """Bump a collection's ``updated_at`` after a write to its CHILD rows only (the schema diff).

        The ORM ``onupdate`` fires only when a collection column changes; a schema PATCH edits
        ``metadata_field`` rows alone, so this keeps ``updated_at`` (and the change stamp built on it)
        honest about "the collection's contract changed".
        """
        await session.execute(
            update(Collection)
            .where(Collection.id == collection_id)
            .values(updated_at=func.clock_timestamp())
        )

    @staticmethod
    async def change_stamp(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> tuple[object, int, object] | None:
        """
        Read a collection's cheap change stamp in ONE aggregate query, or None when it is gone.

        The stamp is ``(collection.updated_at, document count, max(document.updated_at))``: it moves
        on a collection/schema PATCH (both bump ``collection.updated_at``), on a document admission or
        delete (the count), and on any document write — ingestion status transitions and metadata
        value edits bump ``document.updated_at``. Compared for EQUALITY, never ordering.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection to stamp.

        Returns:
            tuple | None: The stamp, or None when the collection does not exist.
        """
        # 1. LEFT JOIN so an empty collection still stamps (count 0, max NULL).
        result = await session.execute(
            select(Collection.updated_at, func.count(Document.id), func.max(Document.updated_at))
            .outerjoin(Document, Document.collection_id == Collection.id)
            .where(Collection.id == collection_id)
            .group_by(Collection.id)
        )
        row = result.first()
        return None if row is None else (row[0], int(row[1]), row[2])

    @staticmethod
    async def set_title_field(
        session: AsyncSession, collection_id: uuid.UUID, title_field: str | None
    ) -> None:
        """Set the collection's display-title field (None clears it → the parsed title is shown).

        Like ``set_estimate_overrides`` this ALWAYS writes, so None is an explicit clear. The name is a
        soft reference to a document-scope ``metadata_field`` — validated by the caller, not by a FK.
        """
        collection = await session.get(Collection, collection_id)
        if collection is None:
            return
        collection.title_field = title_field

    @staticmethod
    async def delete(session: AsyncSession, collection_id: uuid.UUID) -> bool:
        """Delete a collection (cascading its schema, documents, jobs); return whether it existed."""
        collection = await session.get(Collection, collection_id)
        if collection is None:
            return False
        await session.delete(collection)
        return True

    # -------------------- metadata schema --------------------
    @staticmethod
    async def get_schema(session: AsyncSession, collection_id: uuid.UUID) -> list[MetadataField]:
        """Return the collection's metadata field definitions."""
        result = await session.execute(
            select(MetadataField).where(MetadataField.collection_id == collection_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_schemas_by_collections(
        session: AsyncSession, collection_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[MetadataField]]:
        """Return the metadata schema of several collections in ONE query, grouped by collection id.

        The batched counterpart of ``get_schema`` for the fleet-list path: a single SELECT over all
        the given collections (instead of one round-trip per collection — the N+1 the list rendering
        used to pay), grouped in memory. Every requested id is PRESENT in the result — an empty list
        when the collection has no fields — so the caller indexes it directly without a missing-key
        guard.

        Args:
            session (AsyncSession): The active DB session.
            collection_ids (list[uuid.UUID]): The collections whose schemas to fetch.

        Returns:
            dict[uuid.UUID, list[MetadataField]]: collection id → its metadata field rows ([] when none).
        """
        # 1. Empty input → empty map (skip a pointless ``IN ()`` round-trip).
        if not collection_ids:
            return {}
        # 2. One SELECT across every requested collection.
        result = await session.execute(
            select(MetadataField).where(MetadataField.collection_id.in_(collection_ids))
        )
        # 3. Pre-seed every requested id so a collection with no fields still maps to an empty list,
        #    then group the rows in memory (preserving the DB return order within each collection).
        grouped: dict[uuid.UUID, list[MetadataField]] = {cid: [] for cid in collection_ids}
        for row in result.scalars().all():
            grouped[row.collection_id].append(row)
        return grouped

    @staticmethod
    async def replace_schema(
        session: AsyncSession, collection_id: uuid.UUID, fields: list[MetadataField]
    ) -> None:
        """Replace the collection's whole metadata schema with ``fields``."""
        await session.execute(
            delete(MetadataField).where(MetadataField.collection_id == collection_id)
        )
        session.add_all(fields)

    # -------------------- config history --------------------
    @staticmethod
    async def add_config_version(session: AsyncSession, version: ConfigVersion) -> ConfigVersion:
        """Append an immutable config snapshot and return it."""
        session.add(version)
        await session.flush()
        return version

    @staticmethod
    async def list_config_versions(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[ConfigVersion]:
        """Return the collection's config snapshots, newest first."""
        result = await session.execute(
            select(ConfigVersion)
            .where(ConfigVersion.collection_id == collection_id)
            .order_by(ConfigVersion.version.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def max_config_version(session: AsyncSession, collection_id: uuid.UUID) -> int:
        """The highest config version number for a collection (0 when none) — a single scalar,
        so the next-version bump never materializes the whole {pipeline, search} snapshot history."""
        result = await session.execute(
            select(func.max(ConfigVersion.version)).where(
                ConfigVersion.collection_id == collection_id
            )
        )
        return result.scalar_one_or_none() or 0


__all__ = ["CollectionApi"]
