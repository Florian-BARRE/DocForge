# ====== Code Summary ======
# AuthApi — the data-access API for the authentication domain: user accounts and their API keys.
# `get_key_by_hash` is the hot path of every authenticated request; `revoke_key` is a soft delete
# (sets revoked_at). Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import ApiKey, AppUser


class AuthApi:
    """Static data-access API for user accounts and API keys."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuthApi is a static-only class and cannot be instantiated.")

    # -------------------- users --------------------
    @staticmethod
    async def create_user(session: AsyncSession, user: AppUser) -> AppUser:
        """Insert a user and return it (flushed)."""
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def get_user(session: AsyncSession, user_id: uuid.UUID) -> AppUser | None:
        """Fetch a user by id, or None."""
        return await session.get(AppUser, user_id)

    @staticmethod
    async def get_user_by_username(session: AsyncSession, username: str) -> AppUser | None:
        """Fetch a user by username, or None."""
        result = await session.execute(select(AppUser).where(AppUser.username == username))
        return result.scalar_one_or_none()

    # -------------------- api keys --------------------
    @staticmethod
    async def create_key(session: AsyncSession, key: ApiKey) -> ApiKey:
        """Insert an API key and return it (flushed)."""
        session.add(key)
        await session.flush()
        return key

    @staticmethod
    async def get_key_by_hash(session: AsyncSession, key_hash: str) -> ApiKey | None:
        """Fetch an API key by its hash — the authentication hot path."""
        result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_keys(session: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
        """Return a user's API keys, newest first."""
        result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def revoke_key(session: AsyncSession, key_id: uuid.UUID, at: datetime) -> None:
        """Soft-revoke an API key by stamping its revoked_at."""
        key = await session.get(ApiKey, key_id)
        if key is not None:
            key.revoked_at = at


__all__ = ["AuthApi"]
