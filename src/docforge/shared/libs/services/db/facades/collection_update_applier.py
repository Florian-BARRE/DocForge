# ====== Code Summary ======
# CollectionUpdateApplier — the transactional schema/PATCH writers of a collection: the standalone
# schema diff (snippet applier path) and the all-or-nothing PATCH that stages identity/limits, the
# schema diff, the config blobs (+ snapshot), the estimate overrides and the display-title field on
# ONE session, then derives needs_reindex once over the fully-staged state.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import MetadataField

# ====== Local Project Imports ======
from .collection_config_writer import CollectionConfigWriter
from .collection_name_conflict import CollectionNameConflict, DuplicateCollectionNameError
from .collection_schema_diff import CollectionSchemaDiff
from .helpers import DatabaseHelpers
from .payloads import CollectionUpdateResult, CollectionUpdateSpec


class CollectionUpdateApplier(LoggerClass):
    """Single-transaction schema diff and collection PATCH, with the derived needs_reindex."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth the patch is staged and committed on.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

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
            await CollectionSchemaDiff.apply(session, collection_id, desired)
            await CollectionSchemaDiff.clear_orphaned_title_field(session, collection_id)
            reindex_needed = await CollectionConfigWriter.sync_needs_reindex(session, collection_id)
        self.logger.info(
            f"Schema updated for {collection_id} "
            f"({len(desired)} fields, reindex_needed={reindex_needed})"
        )
        return reindex_needed

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
                    await CollectionSchemaDiff.apply(
                        session, collection_id, spec.schema_fields, spec.schema_renames
                    )
                    if spec.schema_renames:
                        await CollectionSchemaDiff.follow_renamed_title_field(
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
                    await CollectionSchemaDiff.clear_orphaned_title_field(session, collection_id)

                # 6. DERIVE needs_reindex ONCE over the fully-staged state (schema + config) vs the
                #    indexed baseline — a single source of truth, never a sticky True. Skipped when the
                #    PATCH touched neither surface (a contract/overrides-only edit can't affect it).
                if spec.schema_fields is not None or spec.config_touched:
                    reindex_needed = await CollectionConfigWriter.sync_needs_reindex(
                        session, collection_id
                    )
        except IntegrityError as error:
            if (
                spec.contract_touched
                and spec.name is not None
                and CollectionNameConflict.is_duplicate_name(error)
            ):
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


__all__ = ["CollectionUpdateApplier"]
