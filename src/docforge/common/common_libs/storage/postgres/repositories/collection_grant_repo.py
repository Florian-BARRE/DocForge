# ====== Code Summary ======
# CollectionGrantRepository — data-access layer for the collection_grant table.
# Implements the GitHub-collaborator model: one role per (user, collection). Upsert
# relies on the unique (user_id, collection_id) constraint; listing helpers back the
# "collaborators of a collection" and "collections of a user" views.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from common_libs.storage.postgres.models import CollectionGrantModel


class CollectionGrantRepository(LoggerClass):
    """
    CRUD operations for the ``collection_grant`` table.

    Each row grants one user a single role on one collection. At most one grant exists
    per (user, collection); re-granting updates that row rather than inserting a duplicate.
    """

    def __init__(self) -> None:
        """Initialize the CollectionGrantRepository logger."""
        LoggerClass.__init__(self)

    async def get(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> CollectionGrantModel | None:
        """
        Fetch the grant a user holds on a collection, if any.

        This is the authorization lookup: a None result means "no access".

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): The user.
            collection_id (uuid.UUID): The collection.

        Returns:
            CollectionGrantModel | None: The grant, or None if the user has no grant.
        """
        result = await session.execute(
            select(CollectionGrantModel)
            .where(CollectionGrantModel.user_id == user_id)
            .where(CollectionGrantModel.collection_id == collection_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
        role: str,
        granted_by: uuid.UUID | None,
    ) -> CollectionGrantModel:
        """
        Create the grant or update its role/granter if one already exists.

        Idempotent on (user_id, collection_id): conflicts on the unique constraint update
        the existing row's ``role`` and ``granted_by`` instead of inserting a duplicate.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): Grantee.
            collection_id (uuid.UUID): Target collection.
            role (str): Per-collection role — a ``GrantRole`` value.
            granted_by (uuid.UUID | None): User who granted it (None = unknown/system).

        Returns:
            CollectionGrantModel: The created or updated grant.
        """
        # 1. INSERT ... ON CONFLICT (user_id, collection_id) DO UPDATE — atomic upsert
        stmt = (
            pg_insert(CollectionGrantModel)
            .values(
                user_id=user_id,
                collection_id=collection_id,
                role=role,
                granted_by=granted_by,
            )
            .on_conflict_do_update(
                constraint="uq_collection_grant_user_collection",
                set_={"role": role, "granted_by": granted_by},
            )
        )
        await session.execute(stmt)
        await session.flush()

        # 2. Return the resulting row (created or updated)
        grant = await self.get(session, user_id, collection_id)
        self.logger.info(
            f"Upserted grant user_id={user_id} collection_id={collection_id} role={role!r}"
        )
        return grant  # type: ignore[return-value]  # guaranteed present after upsert+flush

    async def delete(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> bool:
        """
        Revoke a user's grant on a collection.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): The user.
            collection_id (uuid.UUID): The collection.

        Returns:
            bool: True if a grant row was deleted, False if none existed.
        """
        # 1. Delete the single matching grant
        result = await session.execute(
            sa_delete(CollectionGrantModel)
            .where(CollectionGrantModel.user_id == user_id)
            .where(CollectionGrantModel.collection_id == collection_id)
        )
        deleted = (result.rowcount or 0) > 0
        if deleted:
            self.logger.info(
                f"Deleted grant user_id={user_id} collection_id={collection_id}"
            )
        return deleted

    async def list_for_collection(
        self, session: AsyncSession, collection_id: uuid.UUID
    ) -> list[CollectionGrantModel]:
        """
        List all grants on a collection — its collaborators.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): The collection.

        Returns:
            list[CollectionGrantModel]: Grants for the collection (oldest first).
        """
        result = await session.execute(
            select(CollectionGrantModel)
            .where(CollectionGrantModel.collection_id == collection_id)
            .order_by(CollectionGrantModel.created_at)
        )
        return list(result.scalars().all())

    async def list_collection_ids_for_user(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """
        Return the ids of every collection a user has any grant on.

        Backs scoping a user's visible collections without loading full grant rows.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): The user.

        Returns:
            list[uuid.UUID]: Collection ids the user can access.
        """
        result = await session.execute(
            select(CollectionGrantModel.collection_id)
            .where(CollectionGrantModel.user_id == user_id)
        )
        return list(result.scalars().all())
