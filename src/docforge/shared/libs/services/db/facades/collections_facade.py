# ====== Code Summary ======
# CollectionsFacade — the collection lifecycle across the three stores, exposed as ONE façade
# (``Database.collections``). It owns the reads and the simple single-statement writes (contract,
# estimate overrides, config blobs + CAS head) and delegates the cohesive multi-step operations:
# CollectionCreator (fail-fast create + snapshot), CollectionUpdateApplier (schema diff + atomic PATCH),
# CollectionStoreReconciler (Qdrant ↔ schema) and CollectionDeleter (coherent cross-store delete). The
# Qdrant collection itself is created lazily at first indexing (ensure is idempotent).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import Collection, MetadataField
from shared_libs.services.db.qdrant import QdrantClient, QdrantCollectionApi
from shared_libs.services.db.s3 import S3Client

# ====== Local Project Imports ======
from .collection_config_writer import CollectionConfigWriter
from .collection_creator import CollectionCreator
from .collection_deleter import CollectionDeleter
from .collection_name_conflict import DuplicateCollectionNameError
from .collection_store_reconciler import CollectionStoreReconciler
from .collection_update_applier import CollectionUpdateApplier
from .config_history_payloads import ConfigAuthor
from .helpers import DatabaseHelpers
from .payloads import CollectionUpdateResult, CollectionUpdateSpec


class CollectionsFacade(LoggerClass):
    """Collection lifecycle — create (fail-fast), read, update-config (+snapshot), delete."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._creator = CollectionCreator(postgres)
        self._updater = CollectionUpdateApplier(postgres)
        self._store = CollectionStoreReconciler(postgres, qdrant)
        self._deleter = CollectionDeleter(postgres, qdrant, s3)

    async def create(
        self,
        collection: Collection,
        fields: list[MetadataField],
        author: ConfigAuthor | None = None,
    ) -> Collection:
        """Create a collection with its FULL metadata schema — see ``CollectionCreator.create``.

        Raises:
            ValueError: If two searchable fields collide on a vector slug (fail-fast, C4 guard).
            DuplicateCollectionNameError: If this create lost the collection-name UNIQUE race.
        """
        return await self._creator.create(collection, fields, author=author)

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        """Fetch a collection by id."""
        async with self._postgres.session() as session:
            return await CollectionApi.get(session, collection_id)

    async def get_by_name(self, name: str) -> Collection | None:
        """Fetch a collection by its unique name."""
        async with self._postgres.session() as session:
            return await CollectionApi.get_by_name(session, name)

    async def change_stamp(self, collection_id: uuid.UUID) -> tuple[object, int, object] | None:
        """Return the collection's cheap change stamp (see ``CollectionApi.change_stamp``), or None."""
        async with self._postgres.session() as session:
            return await CollectionApi.change_stamp(session, collection_id)

    async def get_schema(self, collection_id: uuid.UUID) -> list[MetadataField]:
        """Return the collection's metadata schema."""
        async with self._postgres.session() as session:
            return await CollectionApi.get_schema(session, collection_id)

    async def get_schemas_by_collections(
        self, collection_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[MetadataField]]:
        """Return several collections' metadata schemas in ONE query (fleet-list path; avoids the N+1).

        The batched counterpart of ``get_schema``: the list endpoint fetches every collection's schema
        in a single round-trip instead of one ``get_schema`` per row. Every requested id is present in
        the map (empty list when the collection has no fields).
        """
        async with self._postgres.session() as session:
            return await CollectionApi.get_schemas_by_collections(session, collection_ids)

    async def list_all(self) -> list[Collection]:
        """Return every collection."""
        async with self._postgres.session() as session:
            return await CollectionApi.list_all(session)

    async def vector_count(self, collection_id: uuid.UUID) -> int:
        """
        Return the number of vector points indexed for a collection (0 when never ingested).

        The raw Qdrant index size the health surface reports — a collection whose Qdrant space is not
        provisioned yet (created but never ingested) counts as 0, never an error.

        Args:
            collection_id (uuid.UUID): The collection whose vector index is measured.

        Returns:
            int: The point count in the collection's Qdrant space (0 when it has none yet).
        """
        return await QdrantCollectionApi.count(
            self._qdrant.raw, DatabaseHelpers.qdrant_collection_name(collection_id)
        )

    async def update_contract(
        self,
        collection_id: uuid.UUID,
        *,
        name: str | None = None,
        supported_formats: list[str] | None = None,
        tags: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        job_timeout_seconds: float | None = None,
        trace_verbosity: str | None = None,
    ) -> None:
        """Patch the collection's identity/limits (None = leave unchanged; tags [] = clear)."""
        async with self._postgres.session() as session:
            await CollectionApi.update(
                session,
                collection_id,
                name=name,
                supported_formats=supported_formats,
                tags=tags,
                max_file_size_bytes=max_file_size_bytes,
                job_timeout_seconds=job_timeout_seconds,
                trace_verbosity=trace_verbosity,
            )

    async def set_estimate_overrides(
        self, collection_id: uuid.UUID, overrides: dict | None
    ) -> None:
        """Replace the collection's cost-estimate overrides (None clears them → global defaults)."""
        async with self._postgres.session() as session:
            await CollectionApi.set_estimate_overrides(session, collection_id, overrides)

    async def update_schema(self, collection_id: uuid.UUID, desired: list[MetadataField]) -> bool:
        """Evolve the metadata schema by DIFF — see ``CollectionUpdateApplier.update_schema``.

        Returns:
            bool: The DERIVED needs_reindex after the diff (baseline-relative, never sticky).

        Raises:
            ValueError: On vector-slug collisions in the desired schema (fail-fast).
        """
        return await self._updater.update_schema(collection_id, desired)

    async def reconcile_store(self, collection_id: uuid.UUID) -> set[str]:
        """Additively align the Qdrant space with the CURRENT schema — see ``CollectionStoreReconciler``.

        Returns:
            set[str]: Fields whose semantic/lexical named vector is missing and needs a reindex.
        """
        return await self._store.reconcile_store(collection_id)

    async def update_config(
        self,
        collection_id: uuid.UUID,
        *,
        pipeline: dict | None = None,
        search: dict | None = None,
        note: str | None = None,
        expected_version: int | None = None,
        author: ConfigAuthor | None = None,
    ) -> bool:
        """Patch the collection's config blobs, append the snapshot, and derive needs_reindex.

        Args:
            expected_version (int | None): Compare-and-swap token (see ``config_head``); None =
                unconditional write.
            author (ConfigAuthor | None): Who made the change, stamped on the new config version.

        Returns:
            bool: The DERIVED needs_reindex after the write (baseline-relative, never sticky).

        Raises:
            ConfigVersionConflictError: When ``expected_version`` is no longer the head version.
        """
        async with self._postgres.session() as session:
            await CollectionConfigWriter.apply(
                session,
                collection_id,
                pipeline=pipeline,
                search=search,
                note=note,
                expected_version=expected_version,
                author=author,
            )
            return await CollectionConfigWriter.sync_needs_reindex(session, collection_id)

    async def config_head(self, collection_id: uuid.UUID) -> tuple[Collection | None, int]:
        """Read the head config version THEN the row — the CAS base of a read-modify-write.

        Version first: a write committing between the two reads leaves the version stale, so the
        later ``update_config(expected_version=...)`` conflicts instead of losing that write.
        """
        async with self._postgres.session() as session:
            version = await CollectionApi.max_config_version(session, collection_id)
            return await CollectionApi.get(session, collection_id), version

    async def apply_update(
        self, collection_id: uuid.UUID, spec: CollectionUpdateSpec
    ) -> CollectionUpdateResult:
        """Apply every PART of a PATCH in ONE transaction — see ``CollectionUpdateApplier``.

        Raises:
            ValueError: On a vector-slug collision in the desired schema (fail-fast, before any write).
            DuplicateCollectionNameError: A rename lost the collection-name UNIQUE race.
        """
        return await self._updater.apply_update(collection_id, spec)

    async def delete(self, collection_id: uuid.UUID) -> bool:
        """Delete a collection everywhere — see ``CollectionDeleter.delete``.

        Raises:
            IndexRebuildActiveError: A rebuild_index job is RUNNING on the collection.
            CollectionAliasedError: Collection aliases still target it.

        Returns:
            bool: Whether the collection existed.
        """
        return await self._deleter.delete(collection_id)


__all__ = ["CollectionsFacade", "DuplicateCollectionNameError"]
