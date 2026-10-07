# ====== Code Summary ======
# RebuildGuard — the ingest-side half of the rebuild admission lock. Every ingest admission (upload,
# single reingest, bulk reingest) calls it INSIDE its own transaction, before inserting its job: it
# takes the collection row FOR SHARE (which conflicts with the rebuild admission's FOR UPDATE) and
# refuses while a rebuild_index job is live. Race-safe: whichever transaction commits second sees the
# other's job row, so no ingest can start after a rebuild was admitted.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis import RebuildJobApi

# ====== Local Project Imports ======
from .index_rebuild_payloads import IndexRebuildActiveError


class RebuildGuard:
    """Static ingest-admission guard against a live index rebuild."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RebuildGuard is a static-only class and cannot be instantiated.")

    @staticmethod
    async def assert_no_rebuild(session: AsyncSession, collection_id: uuid.UUID) -> None:
        """
        Share-lock the collection row and refuse when a rebuild is live.

        Args:
            session (AsyncSession): The ingest admission's transaction (the lock lives until it ends).
            collection_id (uuid.UUID): The collection being ingested into.

        Raises:
            IndexRebuildActiveError: When a rebuild_index job is pending or running.
        """
        # 1. FOR SHARE: waits for an in-flight rebuild admission, blocks a new one until we commit.
        await RebuildJobApi.lock_collection(session, collection_id, exclusive=False)
        # 2. Refuse while a rebuild is live.
        active = await RebuildJobApi.active_rebuild(session, collection_id)
        if active is not None:
            raise IndexRebuildActiveError(collection_id, active.id)


__all__ = ["RebuildGuard"]
