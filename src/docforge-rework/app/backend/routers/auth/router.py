# ====== Code Summary ======
# The keys-management router — create, list and revoke API keys owned by the root account (the
# keys-only model). Creation returns the plaintext exactly once; list and revoke never expose a
# secret. Every route here also sits behind the global authN gate, so a valid key is required to
# manage keys. Fine-grained "admin only" scoping is Lot 2.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import ApiKey

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthKeys
from ...utils.error_handling import auto_handle_errors
from .models import CreatedKey, CreateKeyRequest, KeyInfo

router = APIRouter(prefix="/auth/keys", tags=["auth"])

# The sole account owning keys in the keys-only model.
_ROOT_USERNAME = "root"


async def _require_root_id() -> uuid.UUID:
    """
    Resolve the root account id, or fail with a clear 409 when it is not provisioned.

    Returns:
        uuid.UUID: The root account's id.

    Raises:
        HTTPException: 409 when no root account exists (auth off / no bootstrap token).
    """
    # 1. Keys are always owned by root — it must have been provisioned at startup.
    root = await CONTEXT.database.auth.get_user_by_username(_ROOT_USERNAME)
    if root is None:
        raise HTTPException(
            status_code=409,
            detail="Root account is not provisioned (enable auth and set AUTH_ROOT_TOKEN).",
        )
    return root.id


@router.post("", response_model=CreatedKey, status_code=201)
@auto_handle_errors
async def create_key(payload: CreateKeyRequest) -> CreatedKey:
    """
    Create an API key owned by root and return its plaintext exactly once.

    Args:
        payload (CreateKeyRequest): The key label and optional per-scope permissions.

    Returns:
        CreatedKey: The key metadata plus the one-time plaintext (never recoverable later).
    """
    # 1. Resolve the owning root account.
    root_id = await _require_root_id()

    # 2. Generate a fresh credential — only the prefix + hash are persisted.
    plaintext, prefix, key_hash = AuthKeys.generate_key()

    # 3. Persist the key row.
    created = await CONTEXT.database.auth.create_key(
        ApiKey(
            user_id=root_id,
            name=payload.name,
            key_hash=key_hash,
            prefix=prefix,
            permissions=payload.permissions,
        )
    )
    CONTEXT.logger.info(f"API key '{payload.name}' created (prefix={prefix})")

    # 4. Return the plaintext ONCE — it is never stored and cannot be shown again.
    return CreatedKey(
        id=str(created.id),
        name=created.name,
        prefix=created.prefix,
        permissions=created.permissions,
        created_at=created.created_at,
        key=plaintext,
    )


@router.get("", response_model=list[KeyInfo])
@auto_handle_errors
async def list_keys() -> list[KeyInfo]:
    """
    List root's API keys, newest first — metadata only, never the hash or plaintext.

    Returns:
        list[KeyInfo]: Every key of the root account with its revocation state.
    """
    # 1. Resolve root; without it there simply are no keys to list.
    root_id = await _require_root_id()

    # 2. Read and shape — the hash never leaves the data layer.
    keys = await CONTEXT.database.auth.list_keys(root_id)
    return [
        KeyInfo(
            id=str(k.id),
            name=k.name,
            prefix=k.prefix,
            permissions=k.permissions,
            created_at=k.created_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}", status_code=204)
@auto_handle_errors
async def revoke_key(key_id: uuid.UUID) -> None:
    """
    Soft-revoke an API key (idempotent — stamps revoked_at).

    Args:
        key_id (uuid.UUID): The key to revoke.
    """
    # 1. Stamp the revocation time; the facade no-ops when the key is unknown.
    await CONTEXT.database.auth.revoke_key(key_id, datetime.now(UTC))
    CONTEXT.logger.info(f"API key {key_id} revoked")


__all__ = ["router"]
