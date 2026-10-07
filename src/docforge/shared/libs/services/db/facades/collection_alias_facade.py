# ====== Code Summary ======
# CollectionAliasFacade — the collection-alias lifecycle: resolve names to collection ids (the path
# `{collection_id}` ref resolver and the `alias:<name>` key scopes both read through here, uncached),
# list/inspect aliases, create-or-re-point one atomically under a row lock (the "switch"), delete one,
# and probe the alias namespace when a collection is created/renamed. Only Postgres is touched — an
# alias is a deployment-level name, never a vector-store (Qdrant `col_<hex>` alias) concept.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Callable, Iterable

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import AuthApi, CollectionAliasApi, CollectionApi
from shared_libs.services.db.postgresql.tables import CollectionAlias

# ====== Local Project Imports ======
from .collection_alias_payloads import (
    CollectionAliasConflictError,
    CollectionAliasInUseError,
    CollectionAliasNameClashError,
    CollectionAliasTargetMissingError,
    CollectionAliasWrite,
)

# The alias-name primary key two concurrent creates race on (schema naming convention pk_<table>).
_PK_CONSTRAINT = "pk_collection_alias"

# A hook the caller runs UNDER the alias row lock with the current target (None = the alias is new),
# before anything is written — it raises to refuse (e.g. a scope check on the old target).
AliasAuthorizer = Callable[[uuid.UUID | None], None]


class CollectionAliasFacade(LoggerClass):
    """Resolution, listing and atomic writes of collection aliases."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth store.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

    @staticmethod
    def _is_pk_race(error: IntegrityError) -> bool:
        """True when the IntegrityError is the alias-name primary-key violation (a lost create race)."""
        # 1. asyncpg carries the violated constraint name on the native error nested as __cause__.
        for candidate in (error.orig, getattr(error.orig, "__cause__", None)):
            if getattr(candidate, "constraint_name", None) == _PK_CONSTRAINT:
                return True
        return False

    async def get(self, name: str) -> CollectionAlias | None:
        """One alias by exact name, or None."""
        async with self._postgres.session() as session:
            return await CollectionAliasApi.get(session, name)

    async def targets_of(self, names: Iterable[str]) -> dict[str, uuid.UUID]:
        """Map each existing alias among ``names`` to its target (a missing name = dangling)."""
        async with self._postgres.session() as session:
            return await CollectionAliasApi.targets_of(session, names)

    async def list_all(self) -> list[CollectionAlias]:
        """Every alias, ordered by name."""
        async with self._postgres.session() as session:
            return await CollectionAliasApi.list_all(session)

    async def names_for(self, collection_id: uuid.UUID) -> list[str]:
        """The aliases targeting one collection, sorted."""
        async with self._postgres.session() as session:
            return await CollectionAliasApi.names_for(session, collection_id)

    async def name_is_alias(self, name: str) -> bool:
        """Whether a (prospective) collection name equals an alias, case-insensitively."""
        async with self._postgres.session() as session:
            return await CollectionAliasApi.alias_named(session, name) is not None

    async def set(
        self, name: str, collection_id: uuid.UUID, authorize: AliasAuthorizer | None = None
    ) -> CollectionAliasWrite:
        """
        Create the alias, or atomically re-point it to ``collection_id`` (one transaction, row-locked).

        Args:
            name (str): The alias name (already slug-validated by the caller).
            collection_id (uuid.UUID): The collection the alias must target.
            authorize (AliasAuthorizer | None): Run under the lock with the current target before
                writing; raising aborts (and rolls back) the write.

        Returns:
            CollectionAliasWrite: The new state plus the previous target (None when created).

        Raises:
            CollectionAliasTargetMissingError: The target collection does not exist.
            CollectionAliasNameClashError: A collection is named like the alias.
            CollectionAliasConflictError: A concurrent request created the same alias first.
        """
        try:
            async with self._postgres.session() as session:
                # 1. The target must exist and no collection may carry the alias's name.
                if await CollectionApi.get(session, collection_id) is None:
                    raise CollectionAliasTargetMissingError(collection_id)
                clash = await CollectionAliasApi.collection_named(session, name)
                if clash is not None:
                    raise CollectionAliasNameClashError(name, clash.name)

                # 2. Lock the current row (if any) so a concurrent re-point serialises behind this one,
                #    then let the caller authorize against the target it is about to replace.
                current = await CollectionAliasApi.get_for_update(session, name)
                previous = current.collection_id if current is not None else None
                if authorize is not None:
                    authorize(previous)

                # 3. Re-point in place, or insert; refresh to read the server-set timestamps.
                if current is None:
                    current = await CollectionAliasApi.add(session, name, collection_id)
                else:
                    current.collection_id = collection_id
                    await session.flush()
                await session.refresh(current)
                written = CollectionAliasWrite(
                    name=current.name,
                    collection_id=current.collection_id,
                    previous_collection_id=previous,
                    created_at=current.created_at,
                    updated_at=current.updated_at,
                )
        except IntegrityError as error:
            if not self._is_pk_race(error):
                raise
            raise CollectionAliasConflictError(name) from error
        self.logger.info(f"Collection alias '{name}' → {collection_id} (was {previous})")
        return written

    async def delete(self, name: str, authorize: AliasAuthorizer | None = None) -> bool:
        """
        Delete one alias (row-locked so the authorization sees the target actually removed).

        Args:
            name (str): The alias name.
            authorize (AliasAuthorizer | None): Run under the lock with the current target; raising
                aborts the delete.

        Raises:
            CollectionAliasInUseError: Live keys are still scoped to ``alias:<name>``.

        Returns:
            bool: True when the alias existed and was removed.
        """
        async with self._postgres.session() as session:
            # 1. Lock + authorize against the current target.
            current = await CollectionAliasApi.get_for_update(session, name)
            if current is None:
                return False
            if authorize is not None:
                authorize(current.collection_id)
            # 2. Never free a name live keys still use: whoever re-created it would inherit them.
            in_use = await AuthApi.count_live_keys_naming(session, f"alias:{name}")
            if in_use:
                raise CollectionAliasInUseError(name, in_use)
            await CollectionAliasApi.remove(session, name)
        self.logger.info(f"Collection alias '{name}' deleted")
        return True


__all__ = ["AliasAuthorizer", "CollectionAliasFacade"]
