# ====== Code Summary ======
# ApiKeyRepository — data-access layer for the api_key table.
# Pure storage: it persists pre-computed key hashes and never generates or hashes keys.
# Lookup by hash returns only non-revoked keys (the per-request auth path); revocation
# and last-used tracking are soft, timestamp-based updates.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from common_libs.storage.postgres.models import ApiKeyModel


class ApiKeyRepository(LoggerClass):
    """
    CRUD operations for the ``api_key`` table.

    Stores only the hash of each key (the plaintext is shown once at creation and never
    persisted). Hashing and key generation are the auth layer's responsibility.
    """

    def __init__(self) -> None:
        """Initialize the ApiKeyRepository logger."""
        LoggerClass.__init__(self)

    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        name: str,
        key_hash: str,
        prefix: str,
    ) -> ApiKeyModel:
        """
        Persist a new API key record and return it.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): Owner of the key.
            name (str): Human-readable label.
            key_hash (str): Pre-computed hash of the key (never hashed here).
            prefix (str): First characters of the key, safe to display.

        Returns:
            ApiKeyModel: The created and flushed record.
        """
        # 1. Build and persist the key
        api_key = ApiKeyModel(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
        )
        session.add(api_key)
        await session.flush()

        self.logger.info(
            f"Created api_key id={api_key.id} user_id={user_id} prefix={prefix!r}"
        )
        return api_key

    async def get_by_hash(
        self, session: AsyncSession, key_hash: str
    ) -> ApiKeyModel | None:
        """
        Fetch a non-revoked API key by its hash (the per-request auth lookup).

        Revoked keys (``revoked_at`` set) are deliberately excluded so a revoked key can
        never authenticate.

        Args:
            session (AsyncSession): Active session.
            key_hash (str): Hash to look up.

        Returns:
            ApiKeyModel | None: The active key, or None if absent or revoked.
        """
        result = await session.execute(
            select(ApiKeyModel)
            .where(ApiKeyModel.key_hash == key_hash)
            .where(ApiKeyModel.revoked_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> list[ApiKeyModel]:
        """
        List all API keys owned by a user (newest first), including revoked ones.

        Revoked keys are kept in the listing so the UI can show their audit trail.

        Args:
            session (AsyncSession): Active session.
            user_id (uuid.UUID): Owner of the keys.

        Returns:
            list[ApiKeyModel]: The user's keys.
        """
        result = await session.execute(
            select(ApiKeyModel)
            .where(ApiKeyModel.user_id == user_id)
            .order_by(ApiKeyModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke(
        self, session: AsyncSession, key_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Soft-revoke a key by stamping ``revoked_at`` (idempotent).

        Scoped to ``user_id`` so a user can only revoke their own keys. Already-revoked
        keys are left untouched (their original revocation time is preserved).

        Args:
            session (AsyncSession): Active session.
            key_id (uuid.UUID): Key to revoke.
            user_id (uuid.UUID): Owner — must match for the revoke to apply.

        Returns:
            bool: True if a not-yet-revoked key was revoked, False otherwise.
        """
        # 1. Stamp revoked_at only for the owner's still-active key
        result = await session.execute(
            sa_update(ApiKeyModel)
            .where(ApiKeyModel.id == key_id)
            .where(ApiKeyModel.user_id == user_id)
            .where(ApiKeyModel.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        revoked = (result.rowcount or 0) > 0
        if revoked:
            await session.flush()
            self.logger.info(f"Revoked api_key id={key_id} user_id={user_id}")
        return revoked

    async def touch_last_used(self, session: AsyncSession, key_id: uuid.UUID) -> None:
        """
        Record that a key was just used by stamping ``last_used_at``.

        Best-effort telemetry on the hot auth path: a missing key is silently ignored.

        Args:
            session (AsyncSession): Active session.
            key_id (uuid.UUID): Key that was used.
        """
        # 1. Update last_used_at; a vanished key is a no-op
        await session.execute(
            sa_update(ApiKeyModel)
            .where(ApiKeyModel.id == key_id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await session.flush()
