# ====== Code Summary ======
# CollectionAliasApi — data access for the `collection_alias` table: point lookups (one name, a batch of
# names), the aliases of one / many collections, the locked read-modify-write the re-point runs under,
# and the cross-namespace clash probes (an alias vs a collection name, compared case-insensitively).
# Every method runs in a caller-supplied session so the façade composes them in one transaction.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Iterable

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Local Project Imports ======
from ..tables import Collection, CollectionAlias


class CollectionAliasApi:
    """Static data-access API for collection aliases."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionAliasApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def get(session: AsyncSession, name: str) -> CollectionAlias | None:
        """Fetch one alias by its (exact) name, or None."""
        return await session.get(CollectionAlias, name)

    @staticmethod
    async def get_for_update(session: AsyncSession, name: str) -> CollectionAlias | None:
        """Fetch one alias under a ``FOR UPDATE`` row lock (held until the caller's transaction ends)."""
        result = await session.execute(
            select(CollectionAlias).where(CollectionAlias.name == name).with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def targets_of(session: AsyncSession, names: Iterable[str]) -> dict[str, uuid.UUID]:
        """Map each EXISTING alias among ``names`` to its target collection id (absent = dangling)."""
        wanted = list(set(names))
        if not wanted:
            return {}
        result = await session.execute(
            select(CollectionAlias.name, CollectionAlias.collection_id).where(
                CollectionAlias.name.in_(wanted)
            )
        )
        return {name: collection_id for name, collection_id in result.all()}

    @staticmethod
    async def list_all(session: AsyncSession) -> list[CollectionAlias]:
        """Every alias, ordered by name."""
        result = await session.execute(select(CollectionAlias).order_by(CollectionAlias.name))
        return list(result.scalars().all())

    @staticmethod
    async def names_for(session: AsyncSession, collection_id: uuid.UUID) -> list[str]:
        """The names of the aliases targeting one collection, sorted."""
        result = await session.execute(
            select(CollectionAlias.name)
            .where(CollectionAlias.collection_id == collection_id)
            .order_by(CollectionAlias.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add(session: AsyncSession, name: str, collection_id: uuid.UUID) -> CollectionAlias:
        """Insert a new alias (flushed — a concurrent same-name insert surfaces as IntegrityError)."""
        alias = CollectionAlias(name=name, collection_id=collection_id)
        session.add(alias)
        await session.flush()
        return alias

    @staticmethod
    async def remove(session: AsyncSession, name: str) -> bool:
        """Delete one alias; True when it existed."""
        result = await session.execute(delete(CollectionAlias).where(CollectionAlias.name == name))
        return result.rowcount > 0

    @staticmethod
    async def collection_named(session: AsyncSession, name: str) -> Collection | None:
        """The collection whose name equals ``name`` case-insensitively (the alias-clash probe)."""
        result = await session.execute(
            select(Collection).where(func.lower(Collection.name) == name.lower()).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def alias_named(session: AsyncSession, name: str) -> CollectionAlias | None:
        """The alias equal to ``name`` case-insensitively (the collection-name clash probe)."""
        return await session.get(CollectionAlias, name.lower())


__all__ = ["CollectionAliasApi"]
