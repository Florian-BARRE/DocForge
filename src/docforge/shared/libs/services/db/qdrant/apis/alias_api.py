# ====== Code Summary ======
# QdrantAliasApi — the alias layer behind an index rebuild. A DocForge collection is addressed by its
# stable name ``col_<hex>``; before its first rebuild that name IS the physical Qdrant collection, after
# it the name is an ALIAS onto a physical ``col_<hex>_r<ts>``. Qdrant resolves an alias for every data
# op, but deleting an alias NAME is a silent no-op — so a drop must resolve alias → physical first.
# Facts verified on Qdrant 1.19.1: an alias cannot be created over an existing collection name, and
# deleting the physical collection removes the aliases pointing at it.
# Self-heal: a generation is stamped COMPLETE (collection metadata) once fully copied, just before the
# swap. If the stable name ever resolves to nothing while a complete generation exists (a first swap
# crashed between deleting the original and creating the alias), ``resolve_or_adopt`` re-points the
# alias at the newest complete generation. Every path that could CREATE the store or treat a missing
# one as empty (``ensure``, reads, deletes, export, sync) calls it first; plain writes (set_payload,
# update_vectors, upsert) do not — they fail loudly on a missing store rather than create one. A
# partial (unstamped) copy is never adopted.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient, models

# The suffix separating a stable name from its rebuilt physical generations: ``col_<hex>_r<ts>``.
REBUILD_SUFFIX = "_r"
# The collection-metadata key stamped on a generation once its copy finished (adoptable from then on).
COMPLETE_MARKER = "docforge_rebuild_complete"


class QdrantAliasApi:
    """Static alias resolution, atomic swap and leftover cleanup for rebuilt collections."""

    logger = loggerplusplus.bind(identifier="QdrantAliasApi")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantAliasApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def generation_ts(name: str) -> int:
        """The ``<ts>`` of a ``<stable>_r<ts>`` generation name (its creation order)."""
        return int(name.rsplit(REBUILD_SUFFIX, 1)[1])

    @staticmethod
    async def alias_target(client: AsyncQdrantClient, name: str) -> str | None:
        """
        Return the physical collection an alias points at, or None when ``name`` is not an alias.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The stable collection name.

        Returns:
            str | None: The aliased physical collection name, or None.
        """
        aliases = (await client.get_aliases()).aliases
        return next((a.collection_name for a in aliases if a.alias_name == name), None)

    @classmethod
    async def resolve_physical(cls, client: AsyncQdrantClient, name: str) -> str | None:
        """
        Resolve a stable name to the physical collection holding its points.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The stable collection name.

        Returns:
            str | None: The alias target, else ``name`` when it is a physical collection, else None.
        """
        # 1. An alias wins (``collection_exists`` would also say True for it).
        target = await cls.alias_target(client, name)
        if target is not None:
            return target
        # 2. Otherwise the name itself is physical — or there is no space at all.
        return name if await client.collection_exists(name) else None

    @staticmethod
    async def generations(client: AsyncQdrantClient, name: str) -> list[str]:
        """Every physical ``<name>_r*`` generation that exists (current or leftover)."""
        prefix = f"{name}{REBUILD_SUFFIX}"
        listed = (await client.get_collections()).collections
        return [c.name for c in listed if c.name.startswith(prefix)]

    @staticmethod
    async def mark_complete(client: AsyncQdrantClient, name: str) -> None:
        """Stamp a generation as fully copied — from now on it may be adopted under its stable name."""
        await client.update_collection(collection_name=name, metadata={COMPLETE_MARKER: True})

    @staticmethod
    async def is_complete(client: AsyncQdrantClient, name: str) -> bool:
        """Whether a generation carries the completion stamp (a partial copy never does)."""
        metadata = (await client.get_collection(name)).config.metadata or {}
        return bool(metadata.get(COMPLETE_MARKER))

    @classmethod
    async def complete_generations(cls, client: AsyncQdrantClient, name: str) -> list[str]:
        """The stamped generations of a stable name, newest first."""
        complete = [
            g for g in await cls.generations(client, name) if await cls.is_complete(client, g)
        ]
        return sorted(complete, key=cls.generation_ts, reverse=True)

    @classmethod
    async def resolve_or_adopt(cls, client: AsyncQdrantClient, name: str) -> bool:
        """
        Whether a stable name answers — re-adopting a stranded complete generation when it does not.

        The single existence check of every path addressing a collection's store (ensure, search,
        export, sync, browse). Costs one extra listing only when the name is missing (never ingested,
        or stranded); a concurrent adopter winning the alias race is success.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The stable collection name.

        Returns:
            bool: True when ``name`` resolves to a store (after any adoption).
        """
        # 1. The common case: the name (physical or alias) exists.
        if await client.collection_exists(name):
            return True
        # 2. Stranded: adopt the newest COMPLETE generation (never a partial copy).
        complete = await cls.complete_generations(client, name)
        if not complete:
            return False
        try:
            await cls.point_alias(client, name, complete[0], replace=False)
        except Exception:
            # A concurrent adopter (or the swap itself) created the alias first — that is the goal.
            if await client.collection_exists(name):
                return True
            raise
        cls.logger.warning(f"Re-adopted stranded generation '{complete[0]}' under '{name}'")
        return True

    @staticmethod
    async def point_alias(
        client: AsyncQdrantClient, alias: str, target: str, *, replace: bool
    ) -> None:
        """
        Point ``alias`` at ``target`` — atomically re-pointing an existing alias when ``replace``.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            alias (str): The stable name.
            target (str): The physical collection it must resolve to.
            replace (bool): True when the alias already exists (delete + create in ONE request).
        """
        actions: list = []
        if replace:
            actions.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))
            )
        actions.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=target, alias_name=alias)
            )
        )
        await client.update_collection_aliases(change_aliases_operations=actions)

    @classmethod
    async def drop_all(cls, client: AsyncQdrantClient, name: str) -> None:
        """
        Delete everything a stable name owns: its physical collection (through the alias) and every
        leftover rebuild generation — never leak a ``_r*`` collection on a DocForge delete.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The stable collection name.
        """
        # 1. The live physical collection (deleting it also removes the alias).
        physical = await cls.resolve_physical(client, name)
        if physical is not None:
            await client.delete_collection(physical)
        # 2. Any generation an interrupted rebuild left behind.
        for leftover in await cls.generations(client, name):
            if leftover != physical:
                await client.delete_collection(leftover)


__all__ = ["COMPLETE_MARKER", "QdrantAliasApi", "REBUILD_SUFFIX"]
