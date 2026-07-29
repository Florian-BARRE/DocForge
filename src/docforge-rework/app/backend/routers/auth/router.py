# ====== Code Summary ======
# The keys-management router — create, list, revoke and rotate API keys owned by the root account
# (the keys-only model). Creation and rotation return the plaintext exactly once; list and revoke
# never expose a secret. Every route here also sits behind the global authN gate, so a valid key is
# required to manage keys. Fine-grained "admin only" scoping is Lot 2.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import ApiKey

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthKeys, Capability, require
from ...utils.error_handling import auto_handle_errors
from .models import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest

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


def _resolve_rotated_fields(
    payload: RotateKeyRequest, old: ApiKey
) -> tuple[str, dict[str, Any] | None, datetime | None]:
    """
    Resolve the new key's name / permissions blob / expiry, cloning from the source when absent.

    A field is only overridden when the client explicitly provided it (``model_fields_set``); an
    absent field is copied verbatim from the key being rotated. This is required because ``None`` is
    both the default AND a meaningful value (null permissions/expiry).

    Args:
        payload (RotateKeyRequest): The rotate request body.
        old (ApiKey): The source key being rotated.

    Returns:
        tuple[str, dict | None, datetime | None]: The resolved ``(name, permissions_blob,
        expires_at)`` for the replacement key.
    """
    # 1. Which fields did the client actually send? (distinguishes "provided null" from "absent").
    fields_set = payload.model_fields_set

    # 2. Name — keep the source label unless a non-null new one was provided (the name column is
    #    NOT NULL, so an explicit null is treated as "clone", never persisted as None).
    name = payload.name if ("name" in fields_set and payload.name is not None) else old.name

    # 3. Permissions — a provided scope is re-serialized (None → full access); else keep the stored
    #    blob verbatim (already a plain JSONB dict or None).
    if "permissions" in fields_set:
        permissions_blob = (
            payload.permissions.model_dump(mode="json")
            if payload.permissions is not None
            else None
        )
    else:
        permissions_blob = old.permissions

    # 4. Expiry — keep the source expiry unless a new instant (or explicit null) was provided.
    expires_at = payload.expires_at if "expires_at" in fields_set else old.expires_at

    return name, permissions_blob, expires_at


@router.post(
    "", response_model=CreatedKey, status_code=201,
    dependencies=[Depends(require(Capability.ADMIN))],
)
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

    # 3. Persist the key row — the validated scope is stored as a plain JSONB dict (None = full
    #    access, the root shape). model_dump(mode="json") keeps enum members as their string values.
    permissions_blob = (
        payload.permissions.model_dump(mode="json") if payload.permissions is not None else None
    )
    created = await CONTEXT.database.auth.create_key(
        ApiKey(
            user_id=root_id,
            name=payload.name,
            key_hash=key_hash,
            prefix=prefix,
            permissions=permissions_blob,
            expires_at=payload.expires_at,
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
        expires_at=created.expires_at,
        key=plaintext,
    )


@router.get(
    "", response_model=list[KeyInfo],
    dependencies=[Depends(require(Capability.ADMIN))],
)
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
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.delete(
    "/{key_id}", status_code=204,
    dependencies=[Depends(require(Capability.ADMIN))],
)
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


@router.post(
    "/{key_id}/rotate", response_model=CreatedKey, status_code=201,
    dependencies=[Depends(require(Capability.ADMIN))],
)
@auto_handle_errors
async def rotate_key(key_id: uuid.UUID, payload: RotateKeyRequest) -> CreatedKey:
    """
    Rotate an API key: issue a fresh secret (optionally re-scoped) and revoke the old key.

    Absent request fields clone the source key's name / permissions / expiry; provided fields
    override them. The old key is revoked so exactly one active credential survives the rotation.

    Args:
        key_id (uuid.UUID): The active key to rotate.
        payload (RotateKeyRequest): Optional overrides for the replacement key.

    Returns:
        CreatedKey: The replacement key metadata plus its one-time plaintext.

    Raises:
        HTTPException: 404 when the key is unknown or owned by another account; 409 when it is
            already revoked (a terminal state — rotate an active key).
    """
    # 1. Resolve root and load the source key, refusing unknown or cross-tenant keys (404).
    root_id = await _require_root_id()
    old = await CONTEXT.database.auth.get_key(key_id)
    if old is None or old.user_id != root_id:
        raise HTTPException(status_code=404, detail="API key not found.")

    # 2. A revoked key is terminal — rotation applies only to an active key.
    if old.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Cannot rotate an already-revoked key.")

    # 3. Resolve the replacement fields (clone-from-source vs. override) and mint a fresh credential.
    name, permissions_blob, expires_at = _resolve_rotated_fields(payload, old)
    plaintext, prefix, key_hash = AuthKeys.generate_key()
    created = await CONTEXT.database.auth.create_key(
        ApiKey(
            user_id=root_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            permissions=permissions_blob,
            expires_at=expires_at,
        )
    )

    # 4. Revoke the old key — the new secret is now the sole active credential.
    await CONTEXT.database.auth.revoke_key(old.id, datetime.now(UTC))
    CONTEXT.logger.info(f"API key {key_id} rotated → {created.id} (prefix={prefix})")

    # 5. Return the plaintext ONCE — same one-time contract as creation.
    return CreatedKey(
        id=str(created.id),
        name=created.name,
        prefix=created.prefix,
        permissions=created.permissions,
        created_at=created.created_at,
        expires_at=created.expires_at,
        key=plaintext,
    )


__all__ = ["router"]
