# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_auth.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous API-key management (create / list / revoke / rotate) resource: the blocking shell
# over the shared ``_AuthSpecs`` builders.

# ====== Standard Library Imports ======
from datetime import datetime
from types import EllipsisType

# ====== Local Project Imports ======
from ...models._shared import KeyPermissions
from ...models.auth import CreatedKey, CreateKeyRequest, KeyInfo, WhoAmI
from .._base import SyncResource
from .specs import _AuthSpecs


class SyncAuth(SyncResource, _AuthSpecs):
    """Synchronous API-key management (create / list / revoke / rotate)."""

    def create_key(
        self,
        name: str,
        permissions: KeyPermissions | None = None,
        expires_at: datetime | None = None,
    ) -> CreatedKey:
        """
        Create an API key and return its plaintext exactly once.

        Args:
            name (str): Human-readable label for the key.
            permissions (KeyPermissions | None): Scope; ``None`` = full access (root).
            expires_at (datetime | None): Absolute expiry; ``None`` = never expires.

        Returns:
            CreatedKey: The key metadata plus the one-time plaintext (never recoverable later).
        """
        return self._transport.request(
            self._create_spec(
                CreateKeyRequest(name=name, permissions=permissions, expires_at=expires_at)
            ),
            CreatedKey,
        )

    def list_keys(self) -> list[KeyInfo]:
        """
        List the account's API keys — metadata only, never a secret.

        Returns:
            list[KeyInfo]: Every key with its revocation state.
        """
        return self._transport.request(self._list_spec(), list[KeyInfo])

    def revoke_key(self, key_id: str) -> None:
        """
        Soft-revoke an API key (idempotent).

        Args:
            key_id (str): The id of the key to revoke.
        """
        return self._transport.request(self._revoke_spec(key_id), type(None))

    def rotate_key(
        self,
        key_id: str,
        name: str | None | EllipsisType = ...,
        permissions: KeyPermissions | None | EllipsisType = ...,
        expires_at: datetime | None | EllipsisType = ...,
    ) -> CreatedKey:
        """
        Rotate an API key: issue a fresh secret (optionally re-scoped) and revoke the old one.

        Only the arguments you pass are sent; an omitted argument (left as ``...``) is cloned from the
        source key by the backend, while an explicit ``None`` sets that field to its null meaning
        (full access / never expires).

        Args:
            key_id (str): The active key to rotate.
            name (str | None | EllipsisType): New label; omit to keep the source name.
            permissions (KeyPermissions | None | EllipsisType): New scope; omit to keep, ``None`` for
                full access.
            expires_at (datetime | None | EllipsisType): New expiry; omit to keep, ``None`` for never.

        Returns:
            CreatedKey: The replacement key metadata plus its one-time plaintext.
        """
        return self._transport.request(
            self._rotate_spec(key_id, self._build_rotate_request(name, permissions, expires_at)),
            CreatedKey,
        )

    def whoami(self) -> WhoAmI:
        """Report the calling token's capabilities + collection scope (what it may do)."""
        return self._transport.request(self._whoami_spec(), WhoAmI)
