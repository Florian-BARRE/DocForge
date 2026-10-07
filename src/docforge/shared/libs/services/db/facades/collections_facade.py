# ====== Code Summary ======
# CollectionsFacade — the collection lifecycle across the three stores. Creation validates the
# contract fail-fast (vector-slug guard) and snapshots the config; the Qdrant collection itself is
# created lazily at first indexing (ensure is idempotent). Deletion runs the coherent cross-store
# order: drop the derived index first (Qdrant), then the truth (PG cascade), then purge the blobs
# nothing references anymore (the multi-reference safety filter), S3 last — after the PG commit.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared_libs.public_models import FieldScope
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    BlobApi,
    CollectionAliasApi,
    CollectionApi,
    JobApi,
    RebuildJobApi,
)
from shared_libs.services.db.postgresql.tables import (
    Collection,
    ConfigVersion,
    JobStatus,
    MetadataField,
)
from shared_libs.services.db.qdrant import QdrantAliasApi, QdrantClient, QdrantCollectionApi
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .collection_alias_payloads import CollectionAliasedError
from .collection_config_writer import CollectionConfigWriter
from .config_history_payloads import ConfigAuthor
from .helpers import DatabaseHelpers
from .index_rebuild_payloads import IndexRebuildActiveError
from .payloads import CollectionUpdateResult, CollectionUpdateSpec
from .trace_purge import TracePurgeHelper

# The collection-name UNIQUE constraint two concurrent creates race on. Name is stable via the schema
# naming convention (uq_<table>_<column>) → the ``unique=True`` on ``collection.name``. asyncpg carries
# the violated constraint name on its native error, nested as the SQLAlchemy wrapper's ``__cause__``.
_NAME_UNIQUE_CONSTRAINT = "uq_collection_name"


class DuplicateCollectionNameError(Exception):
    """Raised when a create loses the collection-name UNIQUE race — the router maps it to a 409."""

    def __init__(self, name: str) -> None:
        """
        Args:
            name (str): The already-taken collection name.
        """
        super().__init__(f"Collection '{name}' already exists.")
        self.name = name


class CollectionsFacade(LoggerClass):
    """Collection lifecycle — create (fail-fast), read, update-config (+snapshot), delete."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3

    @staticmethod
    def _is_duplicate_name(error: IntegrityError) -> bool:
        """
        Decide whether an IntegrityError is the collection-name UNIQUE violation (a lost create race).

        Args:
            error (IntegrityError): The error raised by the contract INSERT's flush.

        Returns:
            bool: True only when the violated constraint is ``uq_collection_name``.
        """
        # 1. Walk the driver error and its __cause__ (the asyncpg native error carrying constraint_name)
        #    and match the name guard — so an unrelated integrity failure still surfaces as a real error.
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == _NAME_UNIQUE_CONSTRAINT
            for candidate in candidates
        )

    async def create(
        self,
        collection: Collection,
        fields: list[MetadataField],
        author: ConfigAuthor | None = None,
    ) -> Collection:
        """
        Create a collection with its FULL metadata schema (including generated/chunk fields).

        Args:
            collection (Collection): The contract row.
            fields (list[MetadataField]): The whole schema — declared up front so the Qdrant
                vector space is complete at first indexing (named vectors can't be added later).
            author (ConfigAuthor | None): Who created it, stamped on the version-1 snapshot (None =
                a system creation, e.g. an import).

        Returns:
            Collection: The created row (id populated).

        Raises:
            ValueError: If two searchable fields collide on a vector slug (fail-fast, C4 guard).
            DuplicateCollectionNameError: If two creates race on the same name and this one loses the
                UNIQUE constraint (the router maps it to a clean 409, never a 500).
        """
        # 1. Fail fast before anything is written.
        DatabaseHelpers.validate_vector_slugs(fields)
        # 2. Contract + schema + the version-1 snapshot, in one transaction. The name-clash pre-check
        #    lives in the router, but a concurrent create can still slip in between it and this insert —
        #    catch that UNIQUE violation and re-raise it as the domain error the router turns into a 409.
        async with self._postgres.session() as session:
            try:
                created = await CollectionApi.create(session, collection)
            except IntegrityError as error:
                if not self._is_duplicate_name(error):
                    raise
                raise DuplicateCollectionNameError(collection.name) from error
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
                    author_key_id=author.key_id if author is not None else None,
                    author_label=author.label if author is not None else None,
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
        """
        Evolve the metadata schema by DIFF — never a wholesale replace.

        A blind replace would delete every MetadataField row and the CASCADE would destroy
        the stored metadata VALUES of unchanged fields. Instead: match by field_name —
        update flags in place, insert the new, delete only the explicitly removed.

        Args:
            collection_id (uuid.UUID): The collection.
            desired (list[MetadataField]): The target schema (collection_id filled here).

        Returns:
            bool: The DERIVED needs_reindex after the diff — True only when the collection has an
            indexed baseline AND its reindex-relevant surface (semantic/lexical fields or the type of
            such a field, plus the embed space) now differs from it. A filterable-only toggle keeps
            the signature stable (reconciled live), and a never-indexed collection stays False.

        Raises:
            ValueError: On vector-slug collisions in the desired schema (fail-fast).
        """
        # 1. Fail fast before anything is written.
        DatabaseHelpers.validate_vector_slugs(desired)

        # 2. Apply the diff, then DERIVE needs_reindex from the resulting config vs the indexed
        #    baseline — never a sticky True (the standalone path: the snippet schema applier).
        async with self._postgres.session() as session:
            await self._apply_schema_diff(session, collection_id, desired)
            await self._clear_orphaned_title_field(session, collection_id)
            reindex_needed = await CollectionConfigWriter.sync_needs_reindex(session, collection_id)
        self.logger.info(
            f"Schema updated for {collection_id} "
            f"({len(desired)} fields, reindex_needed={reindex_needed})"
        )
        return reindex_needed

    @staticmethod
    async def _apply_schema_diff(
        session: AsyncSession,
        collection_id: uuid.UUID,
        desired: list[MetadataField],
        renames: dict[str, str] | None = None,
    ) -> None:
        """
        Diff-update the metadata schema INSIDE a caller-supplied session (never a wholesale replace).

        The transactional core shared by ``update_schema`` (own session) and ``apply_update`` (one
        session threaded through the whole PATCH). The caller MUST have already validated vector slugs
        (fail-fast, before any write). Never opens or commits a session — it only stages the writes;
        the caller then derives ``needs_reindex`` via ``CollectionConfigWriter.sync_needs_reindex`` over the final state.

        Args:
            session (AsyncSession): The unit of work the whole PATCH shares.
            collection_id (uuid.UUID): The collection.
            desired (list[MetadataField]): The target schema (collection_id filled here), keyed by the
                post-rename names.
            renames (dict[str, str] | None): Current name → new name. A renamed row is UPDATED in place
                (same id → its stored values survive), never deleted + re-added.
        """
        renames = renames or {}
        current = await CollectionApi.get_schema(session, collection_id)
        current_by_name = {row.field_name: row for row in current}
        desired_by_name = {row.field_name: row for row in desired}

        # 1. Delete the removed rows FIRST (values cascade — explicit) and flush, so a rename/add may
        #    reuse a freed name in this transaction without tripping the (collection, name) UNIQUE.
        #    A current row survives by name only when that name is not itself a rename's target.
        kept = set(desired_by_name) - set(renames.values())
        removed = [name for name in current_by_name if name not in kept and name not in renames]
        for name in removed:
            await session.delete(current_by_name.pop(name))
        if removed and renames:
            await session.flush()

        # 2. Renames in two phases (a temporary unique name, then the final one) so a chain or a swap
        #    never collides mid-flush; the row keeps its id, hence its document/chunk values.
        if renames:
            renamed = [current_by_name.pop(old) for old in renames]
            for row in renamed:
                row.field_name = f"__renaming_{row.id}"
            await session.flush()
            for row, new_name in zip(renamed, renames.values(), strict=True):
                row.field_name = new_name
                current_by_name[new_name] = row
            await session.flush()

        # 3. Update in place / insert new.
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
            # Documentation only — excluded from the index signature, so it never flags a reindex.
            row.description = wanted.description

    @staticmethod
    async def _follow_renamed_title_field(
        session: AsyncSession, collection_id: uuid.UUID, renames: dict[str, str]
    ) -> None:
        """
        Point ``title_field`` at its field's new name when that field was renamed (same values).

        Args:
            session (AsyncSession): The unit of work the schema diff was staged on.
            collection_id (uuid.UUID): The collection whose setting may follow.
            renames (dict[str, str]): Current name → new name.
        """
        # 1. Only a title naming a renamed field moves; anything else is left to the orphan check.
        collection = await CollectionApi.get(session, collection_id)
        if collection is not None and collection.title_field in renames:
            collection.title_field = renames[collection.title_field]

    async def _clear_orphaned_title_field(
        self, session: AsyncSession, collection_id: uuid.UUID
    ) -> str | None:
        """
        Clear the display-title field when the staged schema no longer has it as a document field.

        ``title_field`` is a SOFT reference (no FK) to a document-scope ``metadata_field``. A schema
        edit that removes or renames that field, or moves it to chunk scope, must not be blocked — so
        the dangling setting is cleared to NULL in the SAME transaction (the parsed title is shown
        again) and the cleared name is returned so the caller can report it. Must run AFTER the schema
        diff is staged on ``session`` (autoflush makes the staged rows visible to the read). The clear
        is logged as a warning, and the PATCH response shows ``title_field: null``.

        Args:
            session (AsyncSession): The unit of work the schema diff was staged on.
            collection_id (uuid.UUID): The collection whose setting is checked.

        Returns:
            str | None: The cleared field name, or None when the setting was unset or still valid.
        """
        # 1. Nothing configured → nothing can dangle.
        collection = await CollectionApi.get(session, collection_id)
        if collection is None or collection.title_field is None:
            return None

        # 2. Still a document-scope field of the post-diff schema → keep it.
        schema = await CollectionApi.get_schema(session, collection_id)
        if any(
            row.field_name == collection.title_field and row.scope == FieldScope.DOCUMENT
            for row in schema
        ):
            return None

        # 3. Orphaned → clear it alongside the schema edit and say so.
        cleared = collection.title_field
        collection.title_field = None
        self.logger.warning(
            f"Collection {collection_id}: title_field '{cleared}' is no longer a document-scope "
            f"field after the schema change — cleared (documents show their parsed title again)"
        )
        return cleared

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
        if not await QdrantAliasApi.resolve_or_adopt(self._qdrant.raw, name):
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
        """
        Apply every PART of a collection PATCH in ONE Postgres transaction (all-or-nothing).

        Identity/limits, the metadata-schema diff, the config blobs (+ snapshot) and the cost-estimate
        overrides are staged on a SINGLE session and committed together: a failure partway through
        rolls the WHOLE patch back, so a collection is never left half-updated (e.g. contract changed
        but schema not). The Qdrant reconcile + backfill are deliberately NOT folded in — they are
        non-transactional and best-effort, so the caller runs them AFTER this commit.

        Args:
            collection_id (uuid.UUID): The collection being patched.
            spec (CollectionUpdateSpec): The parts to apply (each gated by its own marker).

        Returns:
            CollectionUpdateResult: Whether the schema-diff ran and whether a reindex is due.

        Raises:
            ValueError: On a vector-slug collision in the desired schema (fail-fast, before any write).
        """
        # 1. Fail fast on schema vector-slug collisions BEFORE opening the write transaction, so a
        #    bad schema 422s without touching the DB at all (nothing to roll back).
        if spec.schema_fields is not None:
            DatabaseHelpers.validate_vector_slugs(spec.schema_fields)

        reindex_needed = False
        # A rename to an already-taken name slips past the router's pre-check on a concurrent race and
        # violates uq_collection_name at commit — map it to the same domain 409 as create (never a 500).
        try:
            async with self._postgres.session() as session:
                # 2. Identity/limits (only when the caller marked them touched).
                if spec.contract_touched:
                    await CollectionApi.update(
                        session,
                        collection_id,
                        name=spec.name,
                        supported_formats=spec.supported_formats,
                        tags=spec.tags,
                        max_file_size_bytes=spec.max_file_size_bytes,
                        job_timeout_seconds=spec.job_timeout_seconds,
                        trace_verbosity=spec.trace_verbosity,
                    )

                # 3. Metadata schema by DIFF (stages the schema rows only); a renamed field keeps its
                #    row (and values) and drags the display-title setting along with it.
                if spec.schema_fields is not None:
                    await self._apply_schema_diff(
                        session, collection_id, spec.schema_fields, spec.schema_renames
                    )
                    if spec.schema_renames:
                        await self._follow_renamed_title_field(
                            session, collection_id, spec.schema_renames
                        )
                    await CollectionApi.touch(session, collection_id)

                # 4. Config blobs + immutable snapshot (stages the blobs only).
                if spec.config_touched:
                    await CollectionConfigWriter.apply(
                        session,
                        collection_id,
                        pipeline=spec.pipeline,
                        search=spec.search,
                        note=spec.note,
                        author=spec.author,
                    )

                # 5. Cost-estimate overrides (apply=True writes even a clearing None).
                if spec.apply_overrides:
                    await CollectionApi.set_estimate_overrides(
                        session, collection_id, spec.estimate_overrides
                    )

                # 5b. Display-title field (apply=True writes even a clearing None), then — when the
                #     schema changed OR a title was written — re-check it against the schema IN this
                #     transaction. The router validated the value before the write, outside it, so a
                #     concurrent schema PATCH could have removed the field since; the clear catches it.
                if spec.apply_title_field:
                    await CollectionApi.set_title_field(session, collection_id, spec.title_field)
                if spec.schema_fields is not None or spec.apply_title_field:
                    await self._clear_orphaned_title_field(session, collection_id)

                # 6. DERIVE needs_reindex ONCE over the fully-staged state (schema + config) vs the
                #    indexed baseline — a single source of truth, never a sticky True. Skipped when the
                #    PATCH touched neither surface (a contract/overrides-only edit can't affect it).
                if spec.schema_fields is not None or spec.config_touched:
                    reindex_needed = await CollectionConfigWriter.sync_needs_reindex(
                        session, collection_id
                    )
        except IntegrityError as error:
            if spec.contract_touched and spec.name is not None and self._is_duplicate_name(error):
                raise DuplicateCollectionNameError(spec.name) from error
            raise

        self.logger.info(
            f"Collection {collection_id} patched atomically "
            f"(contract={spec.contract_touched}, schema={spec.schema_fields is not None}, "
            f"config={spec.config_touched}, overrides={spec.apply_overrides}, "
            f"title_field={spec.apply_title_field})"
        )
        return CollectionUpdateResult(
            schema_applied=spec.schema_fields is not None,
            schema_reindex_required=reindex_needed,
        )

    async def _cancel_active_jobs(self, collection_id: uuid.UUID) -> int:
        """
        Force every in-flight job of a collection to CANCELLED — run BEFORE the cascade delete.

        A delete cascade removes the ``job`` rows (and the collection's documents) while a worker may
        still be mid-run, inserting ``job_stage_event`` rows and, at its persist phase, document/chunk
        rows — all FK-referencing the about-to-vanish rows, which raises an IntegrityError in the
        worker. Cancelling first closes that race at the source: the CONDITIONAL ``mark_terminal``
        transition flips each live job to CANCELLED and raises ``cancel_requested``, so a live worker
        aborts its run gracefully at its next stage boundary — before it writes anything the cascade
        will delete (no wasted compute, no crash). Committed in its OWN transaction so the worker can
        actually OBSERVE the flag; the cascade follows. Idempotent: a job that already went terminal
        no longer matches the live-status guard (a clean no-op).

        Args:
            collection_id (uuid.UUID): The collection whose in-flight jobs are stopped.

        Returns:
            int: The number of live jobs transitioned to CANCELLED.
        """
        # 1. List + conditionally terminate the live jobs in one committed transaction.
        cancelled = 0
        now = datetime.now(UTC)
        async with self._postgres.session() as session:
            for job in await JobApi.list_active_for_collection(session, collection_id):
                terminated = await JobApi.mark_terminal(
                    session,
                    job.id,
                    status=JobStatus.CANCELLED,
                    reason="collection deleted — ingestion cancelled",
                    finished_at=now,
                )
                if terminated is not None:
                    cancelled += 1
        # 2. Report how many runs were stopped (the worker aborts each at its next stage boundary).
        if cancelled:
            self.logger.info(
                f"Cancelled {cancelled} in-flight job(s) before deleting collection {collection_id}"
            )
        return cancelled

    async def delete(self, collection_id: uuid.UUID) -> bool:
        """
        Delete a collection everywhere — in-flight jobs cancelled, Qdrant, PG cascade, blob purge.

        Raises:
            IndexRebuildActiveError: A rebuild_index job is RUNNING on the collection.
            CollectionAliasedError: Collection aliases still target it (checked BEFORE any destructive
                step; the RESTRICT FK on collection_alias is only the backstop).

        Returns:
            bool: Whether the collection existed.
        """
        # -1. A RUNNING rebuild owns the store mid-copy/swap: refuse rather than force-cancel it under
        #     its feet (a queued one is safely cancelled below — the worker skips it at dequeue). An
        #     aliased collection is refused too: deleting it would break every key/app bound to the alias.
        async with self._postgres.session() as session:
            aliases = await CollectionAliasApi.names_for(session, collection_id)
            rebuild = await RebuildJobApi.active_rebuild(session, collection_id)
        if aliases:
            raise CollectionAliasedError(collection_id, aliases)
        if rebuild is not None and rebuild.status == JobStatus.RUNNING:
            raise IndexRebuildActiveError(collection_id, rebuild.id)
        # 0. Stop in-flight work FIRST so a live worker aborts before the cascade deletes the rows its
        #    mid-run inserts reference (else an FK IntegrityError in the worker). Committed on its own
        #    so the worker observes the cancel flag; a vanished job at its next boundary is a stop too.
        await self._cancel_active_jobs(collection_id)
        # 1. Drop the derived index first — an orphan Qdrant point would break search hydration.
        await QdrantCollectionApi.drop(
            self._qdrant.raw, DatabaseHelpers.qdrant_collection_name(collection_id)
        )
        # 2. One PG transaction: gather purge candidates, cascade-delete, keep only true orphans.
        async with self._postgres.session() as session:
            collection = await CollectionApi.get(session, collection_id)
            if collection is None:
                return False
            # Capture the collection's job ids BEFORE the cascade removes them — their trace payloads
            # are reclaimed from the object store after the commit (the DB rows cascade; only S3 needs it).
            trace_job_ids = await JobApi.list_job_ids_for_collection(session, collection_id)
            candidates = await BlobApi.collect_hashes_for_collection(session, collection_id)
            await CollectionApi.delete(session, collection_id)
            await session.flush()
            # Guarded purge: the reference re-check lives in the DELETE, so a hash a concurrent ingest
            # re-referenced between the flush and the commit is kept; RETURNING gives the S3 delete set.
            orphans = await BlobApi.delete_unreferenced(session, candidates)
        # 3. S3 last, AFTER the commit — a failed S3 delete only leaves harmless orphan objects.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        # 4. Reclaim the collection's runs' full-trace payloads (best-effort — never fails the delete).
        await TracePurgeHelper.purge(self._postgres, self._s3, trace_job_ids)
        self.logger.info(f"Collection {collection_id} deleted ({len(orphans)} blobs purged)")
        return True


__all__ = ["CollectionsFacade", "DuplicateCollectionNameError"]
