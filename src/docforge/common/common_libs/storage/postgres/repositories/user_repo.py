# ====== Code Summary ======
# UserRepository — data-access layer for the app_user table.
# Pure storage: it persists argon2 hashes produced elsewhere and never hashes or
# verifies passwords itself. Provides lookup, creation, listing, activation toggle,
# idempotent root bootstrap, and password updates.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from common_libs.storage.postgres.models import AppUserModel, UserRole


class UserRepository(LoggerClass):
    """
    CRUD operations for the ``app_user`` table.

    Stores only argon2 password hashes (hashing/verification is the auth layer's job).
    """

    def __init__(self) -> None:
        """Initialize the UserRepository logger."""
        LoggerClass.__init__(self)

    async def get_by_id(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> AppUserModel | None:
        """
        Fetch a user by primary key.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): User primary key.

        Returns:
            AppUserModel | None: The user, or None if not found.
        """
        result = await session.execute(
            select(AppUserModel).where(AppUserModel.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(
        self, session: AsyncSession, username: str
    ) -> AppUserModel | None:
        """
        Fetch a user by their unique username.

        Args:
            session (AsyncSession): Active session.
            username (str): Login handle.

        Returns:
            AppUserModel | None: The user, or None if not found.
        """
        result = await session.execute(
            select(AppUserModel).where(AppUserModel.username == username)
        )
        return result.scalar_one_or_none()

    async def list_users(self, session: AsyncSession) -> list[AppUserModel]:
        """
        Return all users ordered by creation date (newest first).

        Args:
            session (AsyncSession): Active session.

        Returns:
            list[AppUserModel]: All users.
        """
        result = await session.execute(
            select(AppUserModel).order_by(AppUserModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        username: str,
        password_hash: str,
        role: str = UserRole.USER.value,
    ) -> AppUserModel:
        """
        Persist a new user and return the created record.

        Args:
            session (AsyncSession): Active session.
            username (str): Unique login handle.
            password_hash (str): Pre-computed argon2 hash (never hashed here).
            role (str): Global role — ``UserRole`` value; defaults to ``user``.

        Returns:
            AppUserModel: The created and flushed record.
        """
        # 1. Build and persist the user (flush to allocate its id for downstream FKs)
        user = AppUserModel(
            username=username,
            password_hash=password_hash,
            role=role,
        )
        session.add(user)
        await session.flush()

        self.logger.info(f"Created user id={user.id} username={username!r} role={role!r}")
        return user

    async def set_active(
        self, session: AsyncSession, user_id: uuid.UUID, is_active: bool
    ) -> AppUserModel | None:
        """
        Enable or disable a user (soft account toggle).

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): Target user.
            is_active (bool): New active state.

        Returns:
            AppUserModel | None: The updated user, or None if not found.
        """
        # 1. Apply the flag; bail out if no row matched
        result = await session.execute(
            sa_update(AppUserModel)
            .where(AppUserModel.id == user_id)
            .values(is_active=is_active)
        )
        if (result.rowcount or 0) == 0:
            return None
        await session.flush()

        # 2. Return the refreshed record
        self.logger.info(f"User id={user_id} is_active={is_active}")
        return await self.get_by_id(session, user_id)

    async def update_password(
        self, session: AsyncSession, user_id: uuid.UUID, password_hash: str
    ) -> AppUserModel | None:
        """
        Replace a user's stored password hash.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): Target user.
            password_hash (str): Pre-computed argon2 hash (never hashed here).

        Returns:
            AppUserModel | None: The updated user, or None if not found.
        """
        # 1. Apply the new hash; bail out if no row matched
        result = await session.execute(
            sa_update(AppUserModel)
            .where(AppUserModel.id == user_id)
            .values(password_hash=password_hash)
        )
        if (result.rowcount or 0) == 0:
            return None
        await session.flush()

        # 2. Return the refreshed record
        self.logger.info(f"Password updated for user id={user_id}")
        return await self.get_by_id(session, user_id)

    async def upsert_root(
        self, session: AsyncSession, *, username: str, password_hash: str
    ) -> AppUserModel:
        """
        Idempotently create or update the single root user (bootstrap).

        Called at startup to guarantee a root account exists. If a user with the given
        username already exists, its password hash is refreshed and the root role +
        active flag are (re)asserted; otherwise a new root user is created. Always
        returns a user with ``role=root`` and ``is_active=True``.

        Args:
            session (AsyncSession): Active session.
            username (str): Root login handle.
            password_hash (str): Pre-computed argon2 hash (never hashed here).

        Returns:
            AppUserModel: The created or updated root user.
        """
        # 1. Look up an existing user by username
        existing = await self.get_by_username(session, username)

        # 2. Update path — refresh hash and re-assert root role + active state
        if existing is not None:
            existing.password_hash = password_hash
            existing.role = UserRole.ROOT.value
            existing.is_active = True
            await session.flush()
            self.logger.info(f"Root user updated id={existing.id} username={username!r}")
            return existing

        # 3. Create path — brand-new root user
        root = AppUserModel(
            username=username,
            password_hash=password_hash,
            role=UserRole.ROOT.value,
            is_active=True,
        )
        session.add(root)
        await session.flush()
        self.logger.info(f"Root user created id={root.id} username={username!r}")
        return root
