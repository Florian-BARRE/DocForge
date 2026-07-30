# ====== Code Summary ======
# AuthFacade — user accounts and API keys. Pure Postgres; wraps AuthApi so the app's auth
# dependencies never manage sessions. `get_key_by_hash` is the hot path of every authenticated
# request.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import AuthApi
from shared_libs.services.db.postgresql.tables import ApiKey, AppUser


class AuthFacade(LoggerClass):
    """User accounts + API keys, each call in its own transaction."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    # -------------------- users --------------------
    async def create_user(self, user: AppUser) -> AppUser:
        """Insert a user account."""
        async with self._postgres.session() as session:
            return await AuthApi.create_user(session, user)

    async def get_user(self, user_id: uuid.UUID) -> AppUser | None:
        """Fetch a user by id — the owning-account check on the authentication hot path."""
        async with self._postgres.session() as session:
            return await AuthApi.get_user(session, user_id)

    async def get_user_by_username(self, username: str) -> AppUser | None:
        """Fetch a user by username (the login path)."""
        async with self._postgres.session() as session:
            return await AuthApi.get_user_by_username(session, username)

    # -------------------- api keys --------------------
    async def create_key(self, key: ApiKey) -> ApiKey:
        """Insert an API key (hash-only; the plaintext is shown once by the caller)."""
        async with self._postgres.session() as session:
            return await AuthApi.create_key(session, key)

    async def get_key(self, key_id: uuid.UUID) -> ApiKey | None:
        """Fetch an API key by id — the rotate/ownership-check path."""
        async with self._postgres.session() as session:
            return await AuthApi.get_key(session, key_id)

    async def get_key_by_hash(self, key_hash: str) -> ApiKey | None:
        """Fetch an API key by its hash — the authentication hot path."""
        async with self._postgres.session() as session:
            return await AuthApi.get_key_by_hash(session, key_hash)

    async def get_key_with_user(self, key_hash: str) -> tuple[ApiKey, AppUser] | None:
        """Fetch a key and its owning user in ONE joined session — the authentication hot path."""
        async with self._postgres.session() as session:
            return await AuthApi.get_key_with_user(session, key_hash)

    async def list_keys(self, user_id: uuid.UUID) -> list[ApiKey]:
        """Return a user's API keys, newest first."""
        async with self._postgres.session() as session:
            return await AuthApi.list_keys(session, user_id)

    async def revoke_key(self, key_id: uuid.UUID, at: datetime) -> None:
        """Soft-revoke an API key."""
        async with self._postgres.session() as session:
            await AuthApi.revoke_key(session, key_id, at)

    async def update_key_permissions(self, key_id: uuid.UUID, permissions: dict[str, Any]) -> None:
        """Replace a key's stored permission scope (used to grant ownership of a created collection)."""
        async with self._postgres.session() as session:
            await AuthApi.update_key_permissions(session, key_id, permissions)

    async def touch_key_last_used(self, key_id: uuid.UUID, at: datetime) -> None:
        """Record a key's last successful authentication (own session, targeted UPDATE)."""
        async with self._postgres.session() as session:
            await AuthApi.touch_key_last_used(session, key_id, at)


__all__ = ["AuthFacade"]
