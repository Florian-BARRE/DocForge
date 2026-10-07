# ====== Code Summary ======
# ConfigVersionApi — the read side of a collection's config history (config_version): a newest-first
# page (+ one extra older row so the caller can summarise the oldest item against its predecessor),
# the row count, and a single version by number. Writes stay in CollectionApi.add_config_version (the
# locked CollectionConfigWriter path). Every method runs in a caller-supplied session.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Local Project Imports ======
from ..tables import ConfigVersion


class ConfigVersionApi:
    """Static read queries over the ``config_version`` history table."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigVersionApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def page(
        session: AsyncSession, collection_id: uuid.UUID, limit: int, offset: int
    ) -> list[ConfigVersion]:
        """
        Return up to ``limit + 1`` snapshots newest-first, starting at ``offset``.

        The extra (older) row is the predecessor of the page's last item — the caller uses it to
        summarise that item's change and drops it from the page.

        Args:
            session (AsyncSession): The unit of work.
            collection_id (uuid.UUID): The collection whose history is read.
            limit (int): The page size.
            offset (int): The number of newer versions to skip.

        Returns:
            list[ConfigVersion]: At most ``limit + 1`` rows, newest first.
        """
        result = await session.execute(
            select(ConfigVersion)
            .where(ConfigVersion.collection_id == collection_id)
            .order_by(ConfigVersion.version.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        return list(result.scalars().all())

    @staticmethod
    async def count(session: AsyncSession, collection_id: uuid.UUID) -> int:
        """The number of config versions recorded for a collection."""
        result = await session.execute(
            select(func.count())
            .select_from(ConfigVersion)
            .where(ConfigVersion.collection_id == collection_id)
        )
        return int(result.scalar_one())

    @staticmethod
    async def get(
        session: AsyncSession, collection_id: uuid.UUID, version: int
    ) -> ConfigVersion | None:
        """One config version by its per-collection number (None when it does not exist)."""
        result = await session.execute(
            select(ConfigVersion).where(
                ConfigVersion.collection_id == collection_id,
                ConfigVersion.version == version,
            )
        )
        return result.scalar_one_or_none()


__all__ = ["ConfigVersionApi"]
