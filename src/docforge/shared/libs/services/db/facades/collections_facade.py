# ====== Code Summary ======
# CollectionsFacade — the collection lifecycle across the three stores. Creation validates the
# contract fail-fast (vector-slug guard) and snapshots the config; the Qdrant collection itself is
# created lazily at first indexing (ensure is idempotent). Deletion runs the coherent cross-store
# order: drop the derived index first (Qdrant), then the truth (PG cascade), then purge the blobs
# nothing references anymore (the multi-reference safety filter), S3 last — after the PG commit.

# ====== Standard Library Imports ======
import uuid

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import BlobApi, CollectionApi
from shared_libs.services.db.postgresql.tables import Collection, ConfigVersion, MetadataField
from shared_libs.services.db.qdrant import QdrantClient, QdrantCollectionApi
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


class CollectionsFacade(LoggerClass):
    """Collection lifecycle — create (fail-fast), read, update-config (+snapshot), delete."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3

    async def create(self, collection: Collection, fields: list[MetadataField]) -> Collection:
        """
        Create a collection with its FULL metadata schema (including generated/chunk fields).

        Args:
            collection (Collection): The contract row.
            fields (list[MetadataField]): The whole schema — declared up front so the Qdrant
                vector space is complete at first indexing (named vectors can't be added later).

        Returns:
            Collection: The created row (id populated).

        Raises:
            ValueError: If two searchable fields collide on a vector slug (fail-fast, C4 guard).
        """
        # 1. Fail fast before anything is written.
        DatabaseHelpers.validate_vector_slugs(fields)
        # 2. Contract + schema + the version-1 snapshot, in one transaction.
        async with self._postgres.session() as session:
            created = await CollectionApi.create(session, collection)
            for field in fields:
                field.collection_id = created.id
            await CollectionApi.replace_schema(session, created.id, fields)
            await CollectionApi.add_config_version(
                session,
                ConfigVersion(
                    collection_id=created.id,
                    version=1,
                    config={"pipeline": created.pipeline, "search": created.search},
                    note="creation",
                ),
            )
        self.logger.info(f"Collection '{collection.name}' created with {len(fields)} fields")
        return created

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        """Fetch a collection by id."""
        async with self._postgres.session() as session:
            return await CollectionApi.get(session, collection_id)

    async def get_by_name(self, name: str) -> Collection | None:
        """Fetch a collection by its unique name."""
        async with self._postgres.session() as session:
            return await CollectionApi.get_by_name(session, name)

    async def get_schema(self, collection_id: uuid.UUID) -> list[MetadataField]:
        """Return the collection's metadata schema."""
        async with self._postgres.session() as session:
            return await CollectionApi.get_schema(session, collection_id)

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
        max_file_size_bytes: int | None = None,
        job_timeout_seconds: float | None = None,
    ) -> None:
        """Patch the collection's identity/limits (None = leave unchanged)."""
        async with self._postgres.session() as session:
            await CollectionApi.update(
                session,
                collection_id,
                name=name,
                supported_formats=supported_formats,
                max_file_size_bytes=max_file_size_bytes,
                job_timeout_seconds=job_timeout_seconds,
            )

    async def set_estimate_overrides(
        self, collection_id: uuid.UUID, overrides: dict | None
    ) -> None:
        """Replace the collection's cost-estimate overrides (None clears them → global defaults)."""
        async with self._postgres.session() as session:
            await CollectionApi.set_estimate_overrides(session, collection_id, overrides)

    async def update_schema(self, collection_id: uuid.UUID, desired: list[MetadataField]) -> bool:
        """
        Evolve the metadata schema by DIFF — never a wholesale replace.

        A blind replace would delete every MetadataField row and the CASCADE would destroy
        the stored metadata VALUES of unchanged fields. Instead: match by field_name —
        update flags in place, insert the new, delete only the explicitly removed.

        Args:
            collection_id (uuid.UUID): The collection.
            desired (list[MetadataField]): The target schema (collection_id filled here).

        Returns:
            bool: True when the SEARCHABLE surface changed (semantic/lexical/filterable or
            the type of such a field) — the caller flags needs_reindex; plain metadata
            edits do not require a reindex.

        Raises:
            ValueError: On vector-slug collisions in the desired schema (fail-fast).
        """
        # 1. Fail fast before anything is written.
        DatabaseHelpers.validate_vector_slugs(desired)

        async with self._postgres.session() as session:
            current = await CollectionApi.get_schema(session, collection_id)
            current_by_name = {row.field_name: row for row in current}
            desired_by_name = {row.field_name: row for row in desired}

            # 2. The searchable surface before/after — membership drives the reindex flag.
            def searchable(rows: dict[str, MetadataField]) -> set[tuple]:
                return {
                    (r.field_name, r.field_type, r.semantic, r.lexical, r.filterable)
                    for r in rows.values()
                    if r.semantic or r.lexical or r.filterable
                }

            reindex_needed = searchable(current_by_name) != searchable(desired_by_name)

            # 3. Update in place / insert new / delete removed (values cascade — explicit).
            for name, wanted in desired_by_name.items():
                row = current_by_name.get(name)
                if row is None:
                    wanted.collection_id = collection_id
                    session.add(wanted)
                    continue
                row.field_type = wanted.field_type
                row.required = wanted.required
                row.filterable = wanted.filterable
                row.lexical = wanted.lexical
                row.semantic = wanted.semantic
                row.enum_values = wanted.enum_values
                row.origin = wanted.origin
                row.scope = wanted.scope
            for name, row in current_by_name.items():
                if name not in desired_by_name:
                    await session.delete(row)

            # 4. A changed searchable surface invalidates the vector space.
            if reindex_needed:
                await CollectionApi.update(session, collection_id, needs_reindex=True)
        self.logger.info(
            f"Schema updated for {collection_id} "
            f"({len(desired)} fields, reindex_needed={reindex_needed})"
        )
        return reindex_needed

    async def reconcile_store(self, collection_id: uuid.UUID) -> set[str]:
        """
        Additively reconcile the Qdrant collection with the CURRENT metadata schema (idempotent).

        The store-side counterpart of a schema edit: a field toggled ``filterable`` after first
        ingest gets its payload index added LIVE (no reindex, no destructive op), so its search
        filter starts matching. A field toggled ``semantic``/``lexical`` needs a named vector, which
        Qdrant cannot add to a live collection — those are returned as reindex-required, never
        silently ignored. A no-op (empty set) when the collection has no Qdrant space yet: the first
        ingest provisions it from the current schema, so nothing is missing to reconcile.

        Args:
            collection_id (uuid.UUID): The collection whose vector store is reconciled.

        Returns:
            set[str]: Fields whose semantic/lexical named vector is missing and needs a reindex
                (empty when nothing is missing or the collection was never ingested).
        """
        # 1. No Qdrant space provisioned yet → the first ingest builds it from the schema; nothing
        #    to reconcile. Guard here so reconcile() can assume the collection exists.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if not await self._qdrant.raw.collection_exists(name):
            return set()
        # 2. Derive the searchable surface from the current schema and additively align the store.
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        reindex_fields = await QdrantCollectionApi.reconcile(
            self._qdrant.raw,
            name,
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
        )
        self.logger.info(
            f"Reconciled Qdrant store for {collection_id} "
            f"(reindex-required fields: {sorted(reindex_fields)})"
        )
        return reindex_fields

    async def update_config(
        self,
        collection_id: uuid.UUID,
        *,
        pipeline: dict | None = None,
        search: dict | None = None,
        needs_reindex: bool | None = None,
        note: str | None = None,
    ) -> None:
        """Patch the collection's config blobs and append the immutable snapshot."""
        async with self._postgres.session() as session:
            # 1. Apply the patch.
            await CollectionApi.update(
                session,
                collection_id,
                pipeline=pipeline,
                search=search,
                needs_reindex=needs_reindex,
            )
            collection = await CollectionApi.get(session, collection_id)
            if collection is None:
                return
            # 2. Snapshot the NEW state (append-only history). Only the max version number is needed —
            #    fetch it as a scalar, not the whole {pipeline, search} snapshot history.
            next_version = await CollectionApi.max_config_version(session, collection_id) + 1
            await CollectionApi.add_config_version(
                session,
                ConfigVersion(
                    collection_id=collection_id,
                    version=next_version,
                    config={"pipeline": collection.pipeline, "search": collection.search},
                    note=note,
                ),
            )

    async def delete(self, collection_id: uuid.UUID) -> bool:
        """
        Delete a collection everywhere — Qdrant first, PG cascade, then the filtered blob purge.

        Returns:
            bool: Whether the collection existed.
        """
        # 1. Drop the derived index first — an orphan Qdrant point would break search hydration.
        await QdrantCollectionApi.drop(
            self._qdrant.raw, DatabaseHelpers.qdrant_collection_name(collection_id)
        )
        # 2. One PG transaction: gather purge candidates, cascade-delete, keep only true orphans.
        async with self._postgres.session() as session:
            collection = await CollectionApi.get(session, collection_id)
            if collection is None:
                return False
            candidates = await BlobApi.collect_hashes_for_collection(session, collection_id)
            await CollectionApi.delete(session, collection_id)
            await session.flush()
            orphans = await BlobApi.find_unreferenced(session, candidates)
            await BlobApi.delete_rows(session, orphans)
        # 3. S3 last, AFTER the commit — a failed S3 delete only leaves harmless orphan objects.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        self.logger.info(f"Collection {collection_id} deleted ({len(orphans)} blobs purged)")
        return True


__all__ = ["CollectionsFacade"]
