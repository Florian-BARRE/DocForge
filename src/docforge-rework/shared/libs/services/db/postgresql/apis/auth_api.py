# ====== Code Summary ======
# AuthApi — the data-access API for the authentication domain: user accounts and their API keys.
# `get_key_by_hash` is the hot path of every authenticated request; `revoke_key` is a soft delete
# (sets revoked_at). Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import select, update
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
    async def get_key(session: AsyncSession, key_id: uuid.UUID) -> ApiKey | None:
        """Fetch an API key by id, or None — the rotate/ownership-check path."""
        return await session.get(ApiKey, key_id)

    @staticmethod
    async def get_key_by_hash(session: AsyncSession, key_hash: str) -> ApiKey | None:
        """Fetch an API key by its hash — the authentication hot path."""
        result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_key_with_user(
        session: AsyncSession, key_hash: str
    ) -> tuple[ApiKey, AppUser] | None:
        """
        Fetch an API key AND its owning user in one joined query — the authentication hot path.

        Folds what used to be two sequential round-trips (key lookup, then owner lookup) into a
        single session/statement. The inner join means a key whose owner row is missing yields no
        result (indistinguishable from an unknown key — both deny with the same opaque 401).

        Args:
            session (AsyncSession): The unit of work.
            key_hash (str): The deterministic hash of the presented bearer token.

        Returns:
            tuple[ApiKey, AppUser] | None: The key and its owner, or None when no key/owner matches.
        """
        # 1. One statement joins the key to its account on the FK.
        result = await session.execute(
            select(ApiKey, AppUser)
            .join(AppUser, ApiKey.user_id == AppUser.id)
            .where(ApiKey.key_hash == key_hash)
        )
        row = result.one_or_none()
        # 2. Unpack the (key, user) pair, or signal "no match" to the caller.
        return None if row is None else (row[0], row[1])

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

    @staticmethod
    async def touch_key_last_used(
        session: AsyncSession, key_id: uuid.UUID, at: datetime
    ) -> None:
        """
        Stamp an API key's last_used_at with a targeted UPDATE (cheapest on the hot path).

        Uses a scoped UPDATE statement rather than loading and merging the row: the caller already
        holds the read row, and this metrics write must be as light as possible.

        Args:
            session (AsyncSession): The unit of work.
            key_id (uuid.UUID): The key that just authenticated.
            at (datetime): The authentication instant to record.
        """
        # 1. One scoped UPDATE — no row load, no ORM merge.
        await session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=at)
        )


__all__ = ["AuthApi"]
