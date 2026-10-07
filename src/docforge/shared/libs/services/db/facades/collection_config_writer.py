# ====== Code Summary ======
# CollectionConfigWriter — the transactional core of every collection config write, staged on a
# caller-supplied session: lock the row, patch the {pipeline, search} blobs, append the immutable
# config_version snapshot (optionally compare-and-swap on the version the caller read), and derive
# ``needs_reindex`` from the final staged state. Shared by the standalone ``update_config`` and the
# one-transaction collection PATCH (``apply_update``) so both mint versions identically.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import ConfigVersion


class ConfigVersionConflictError(Exception):
    """Raised when a compare-and-swap config write finds the version moved since the caller read it."""

    def __init__(self, collection_id: uuid.UUID, expected: int, actual: int) -> None:
        """
        Args:
            collection_id (uuid.UUID): The collection whose config moved.
            expected (int): The config version the caller based its change on.
            actual (int): The config version found under the row lock.
        """
        super().__init__(
            f"Collection {collection_id}: config changed concurrently "
            f"(expected version {expected}, found {actual})."
        )
        self.expected = expected
        self.actual = actual


class CollectionConfigWriter:
    """Static session-scoped config write (lock → patch → snapshot) + needs_reindex derivation."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionConfigWriter is a static-only class and cannot be instantiated.")

    @staticmethod
    async def apply(
        session: AsyncSession,
        collection_id: uuid.UUID,
        *,
        pipeline: dict | None = None,
        search: dict | None = None,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        """
        Patch the config blobs + append the snapshot INSIDE a caller-supplied session.

        Never opens or commits — it only stages the writes; the caller derives ``needs_reindex`` via
        ``sync_needs_reindex`` over the final state.

        Args:
            session (AsyncSession): The caller's unit of work.
            collection_id (uuid.UUID): The collection whose config is written.
            pipeline (dict | None): The new ingestion blob (None = unchanged).
            search (dict | None): The new search blob (None = unchanged).
            note (str | None): The snapshot note.
            expected_version (int | None): Compare-and-swap token — the config version the caller's
                change was computed from. None = unconditional write.

        Raises:
            ConfigVersionConflictError: When ``expected_version`` no longer matches under the lock.
        """
        # 1. Lock the collection row FIRST: concurrent config writes on the same collection serialize
        #    here, so the version counter can't be read-then-bumped by two transactions at once (which
        #    would mint a duplicate (collection_id, version)). The lock is held until the transaction
        #    ends; uq_config_version_collection_id is the DB backstop behind it.
        collection = await CollectionApi.get_for_update(session, collection_id)
        if collection is None:
            return

        # 2. Under the lock, the head version is authoritative: a caller that computed its change on
        #    an older head would silently overwrite a concurrent write (lost update) — refuse instead.
        head = await CollectionApi.max_config_version(session, collection_id)
        if expected_version is not None and head != expected_version:
            raise ConfigVersionConflictError(collection_id, expected_version, head)

        # 3. Apply the patch on the locked row, then snapshot the NEW state (append-only history).
        await CollectionApi.update(session, collection_id, pipeline=pipeline, search=search)
        await CollectionApi.add_config_version(
            session,
            ConfigVersion(
                collection_id=collection_id,
                version=head + 1,
                config={"pipeline": collection.pipeline, "search": collection.search},
                note=note,
            ),
        )

    @staticmethod
    async def sync_needs_reindex(session: AsyncSession, collection_id: uuid.UUID) -> bool:
        """
        Derive ``needs_reindex`` from the CURRENT config vs the indexed baseline — the single source.

        ``needs_reindex`` flips ON only when the collection has an indexed baseline
        (``indexed_signature`` not NULL) AND its current reindex-relevant config (semantic/lexical
        metadata surface + embed vector space; ``filterable`` EXCLUDED — it reconciles live) differs
        from that baseline. So: a never-indexed collection → False; reverting to the indexed config →
        equal signatures → False; a filterable-only toggle → unchanged signature → stays False.

        Must be called AFTER every schema/config write has been staged on the same session, so it
        sees the final state (autoflush makes the staged rows visible to its reads).

        Args:
            session (AsyncSession): The unit of work the write was staged on.
            collection_id (uuid.UUID): The collection to recompute.

        Returns:
            bool: The recomputed ``needs_reindex`` (also written onto the row).
        """
        # 1. Read the post-write config (same identity-mapped row → reflects staged mutations).
        collection = await CollectionApi.get(session, collection_id)
        if collection is None:
            return False
        schema = await CollectionApi.get_schema(session, collection_id)
        # 2. A never-indexed collection has no baseline to be stale against → never needs a reindex.
        current = CollectionIndexSignature.compute(collection.pipeline, schema)
        needs = collection.indexed_signature is not None and current != collection.indexed_signature
        # 3. Stage the derived flag on the row (never a sticky True).
        collection.needs_reindex = needs
        return needs


__all__ = ["CollectionConfigWriter", "ConfigVersionConflictError"]
