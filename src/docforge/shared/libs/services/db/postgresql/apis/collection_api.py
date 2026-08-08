# ====== Code Summary ======
# CollectionApi — the data-access API for the collection domain: the collection itself, its metadata
# SCHEMA (metadata_field), and its config history (config_version). Every method runs in a
# caller-supplied session so the Database façade can compose several apis in one transaction. It
# touches only Postgres; coherence with Qdrant/S3 is the façade's concern.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import Collection, ConfigVersion, MetadataField


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
        max_file_size_bytes: int | None = None,
        job_timeout_seconds: float | None = None,
        pipeline: dict | None = None,
        search: dict | None = None,
        needs_reindex: bool | None = None,
    ) -> None:
        """Patch the provided contract fields on a collection (None means 'leave unchanged')."""
        collection = await session.get(Collection, collection_id)
        if collection is None:
            return
        if name is not None:
            collection.name = name
        if supported_formats is not None:
            collection.supported_formats = supported_formats
        if max_file_size_bytes is not None:
            collection.max_file_size_bytes = max_file_size_bytes
        if job_timeout_seconds is not None:
            collection.job_timeout_seconds = job_timeout_seconds
        if pipeline is not None:
            collection.pipeline = pipeline
        if search is not None:
            collection.search = search
        if needs_reindex is not None:
            collection.needs_reindex = needs_reindex

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
