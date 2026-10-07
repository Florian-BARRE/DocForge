# ====== Code Summary ======
# CollectionStoreSync — the store-side follow-through of a collection write, kept out of router.py
# so the routes stay orchestration. It owns the two side-effecting steps a write triggers: granting
# the creating key ownership of a freshly created collection, and reconciling the Qdrant store to a
# just-edited schema (purging the residue of departed fields first) then enqueuing the idempotent
# repair backfills.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal


class CollectionStoreSync:
    """Static store-side follow-through for collection writes (ownership grant, store reconcile)."""

    logger = loggerplusplus.bind(identifier="CollectionStoreSync")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionStoreSync is a static-only class and cannot be instantiated.")

    @staticmethod
    async def grant_creator_scope(principal: AuthPrincipal, collection_id: str) -> None:
        """
        Append a freshly created collection's id to the creating key's own scope.

        No-op for the full-access principal (auth off / root key) and for wildcard-scoped keys, which
        already cover every collection. Only a list-scoped key needs (and gets) the new id.

        Args:
            principal (AuthPrincipal): The authenticated creator.
            collection_id (str): The new collection's id to bring into the key's scope.
        """
        # 1. Full-access / keyless / permission-less principals need no scoping (app-side guard).
        key = principal.key
        if principal.is_full_access or key is None or key.permissions is None:
            return

        # 2. Delegate the read → append-if-list-scoped-and-absent → persist logic to the store
        #    façade (shared with the async import path); it no-ops on a wildcard scope or a duplicate.
        await CONTEXT.database.auth.grant_collection_to_key(key.id, collection_id)

    @classmethod
    async def purge_departed_fields(cls, collection_id: uuid.UUID, departed: list[str]) -> None:
        """
        Best-effort: clear departed fields' payload keys + meta-vector data from every Qdrant point.

        Runs after the schema commit and NEVER fails the write: a store error is logged, and the
        convergent cleanup (it also clears residue the current schema no longer explains) repairs it
        at the next schema-changing PATCH or snippet import.

        Args:
            collection_id (uuid.UUID): The collection whose points are cleaned.
            departed (list[str]): Field names removed / renamed away by the change.
        """
        # 1. Delegate to the facade; a store failure is reported, never raised to the client.
        try:
            await CONTEXT.database.schema_changes.purge_departed_fields(collection_id, departed)
        except Exception as exc:  # noqa: BLE001 — post-commit, best-effort by contract
            cls.logger.error(
                f"Collection {collection_id}: departed-field Qdrant cleanup failed for {departed} "
                f"({exc}) — stale payload keys/vectors remain until the next schema change re-runs it"
            )

    @classmethod
    async def reconcile_and_backfill(
        cls, collection_id: uuid.UUID, departed: list[str] | None = None
    ) -> None:
        """
        Reconcile the Qdrant store to the current schema and enqueue the repair backfills.

        The store-side follow-through of a schema edit: newly-filterable fields get their payload index
        added live, then the two idempotent backfills repopulate existing points with the new
        denormalised values/vectors. Semantic/lexical fields whose named vector Qdrant cannot add live
        are logged as reindex-required (a reingest is the only fix).

        Args:
            collection_id (uuid.UUID): The collection whose store is reconciled and backfilled.
            departed (list[str] | None): Field names that left the schema — their residue is purged
                first (the purge is convergent, so it also runs with none to heal earlier failures).
        """
        # 0. Clear what departed fields left on the points BEFORE re-adding indexes / repainting.
        await cls.purge_departed_fields(collection_id, departed or [])

        # 1. Additively align the store; surface the fields that truly need a reindex (missing vectors).
        reindex_fields = await CONTEXT.database.collections.reconcile_store(collection_id)
        if reindex_fields:
            cls.logger.warning(
                f"Collection {collection_id}: fields {sorted(reindex_fields)} need a named vector "
                f"Qdrant cannot add to a live collection — reingest to make them searchable"
            )

        # 2. Repopulate existing points with the newly denormalised values/vectors (idempotent, async).
        await CONTEXT.queue.enqueue_backfill(str(collection_id))


__all__ = ["CollectionStoreSync"]
