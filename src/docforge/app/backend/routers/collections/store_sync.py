# ====== Code Summary ======
# CollectionStoreSync — the store-side follow-through of a collection write, kept out of router.py
# so the routes stay orchestration. It owns the two side-effecting steps a write triggers: granting
# the creating key ownership of a freshly created collection, and reconciling the Qdrant store to a
# just-edited schema then enqueuing the idempotent repair backfills.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, KeyPermissions


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
        # 1. Full-access / keyless / permission-less principals need no scoping.
        key = principal.key
        if principal.is_full_access or key is None or key.permissions is None:
            return

        # 2. A wildcard-scoped key already covers everything; only a list-scoped key gains the id.
        scope = KeyPermissions.model_validate(key.permissions)
        if "*" in scope.collections or collection_id in scope.collections:
            return
        scope.collections.append(collection_id)
        await CONTEXT.database.auth.update_key_permissions(key.id, scope.model_dump(mode="json"))

    @classmethod
    async def reconcile_and_backfill(cls, collection_id: uuid.UUID) -> None:
        """
        Reconcile the Qdrant store to the current schema and enqueue the repair backfills.

        The store-side follow-through of a schema edit: newly-filterable fields get their payload index
        added live, then the two idempotent backfills repopulate existing points with the new
        denormalised values/vectors. Semantic/lexical fields whose named vector Qdrant cannot add live
        are logged as reindex-required (a reingest is the only fix).

        Args:
            collection_id (uuid.UUID): The collection whose store is reconciled and backfilled.
        """
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
