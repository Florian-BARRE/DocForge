# ====== Code Summary ======
# The keys-management router — create, list, revoke and rotate API keys owned by the root account
# (the keys-only model). Creation and rotation return the plaintext exactly once; list and revoke
# never expose a secret. Every route demands the ADMIN capability; a SCOPED admin key is further held to
# keys whose scope is a subset of its own (KeyGrantGuard): it can neither mint a broader key (null /
# '*' / foreign collections / capabilities it lacks) nor see, rotate or revoke a key beyond its scope.

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
from ...libs.auth import (
    AuthKeys,
    AuthPrincipal,
    Capability,
    KeyGrantGuard,
    KeyScopeAliases,
    evict_cached_key,
    require,
)
from ...libs.logsafe import LogSafeHelpers
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
            payload.permissions.to_stored() if payload.permissions is not None else None
        )
    else:
        permissions_blob = old.permissions

    # 4. Expiry — keep the source expiry unless a new instant (or explicit null) was provided.
    expires_at = payload.expires_at if "expires_at" in fields_set else old.expires_at

    return name, permissions_blob, expires_at


@router.post("", response_model=CreatedKey, status_code=201)
@auto_handle_errors
async def create_key(
    payload: CreateKeyRequest,
    principal: AuthPrincipal = Depends(require(Capability.ADMIN)),
) -> CreatedKey:
    """
    Create an API key owned by root and return its plaintext exactly once.

    Args:
        payload (CreateKeyRequest): The key label and optional per-scope permissions.

    Returns:
        CreatedKey: The key metadata plus the one-time plaintext (never recoverable later).
    """
    # 1. A scoped caller may only grant a subset of its own scope (403); resolve the owning root
    #    account; every collection alias the scope names must exist (422).
    KeyGrantGuard.assert_can_grant(principal, payload.permissions)
    root_id = await _require_root_id()
    await KeyScopeAliases.validate_scope_entries(payload.permissions)

    # 2. Generate a fresh credential — only the prefix + hash are persisted.
    plaintext, prefix, key_hash = AuthKeys.generate_key()

    # 3. Persist the key row — the validated scope (a profile already expanded to its explicit
    #    capability list) is stored as a plain JSONB dict (None = full access, the root shape).
    permissions_blob = payload.permissions.to_stored() if payload.permissions is not None else None
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
    CONTEXT.logger.info(
        f"API key '{LogSafeHelpers.sanitize(payload.name)}' created (prefix={prefix})"
    )

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


@router.get("", response_model=list[KeyInfo])
@auto_handle_errors
async def list_keys(
    principal: AuthPrincipal = Depends(require(Capability.ADMIN)),
) -> list[KeyInfo]:
    """
    List root's API keys, newest first — metadata only, never the hash or plaintext.

    Returns:
        list[KeyInfo]: Every key of the root account the caller may manage (a scoped admin sees only
        keys whose scope is a subset of its own), with its revocation state.
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
        if KeyGrantGuard.can_manage(principal, k.permissions)
    ]


@router.delete("/{key_id}", status_code=204)
@auto_handle_errors
async def revoke_key(
    key_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.ADMIN)),
) -> None:
    """
    Soft-revoke an API key (idempotent — stamps revoked_at).

    Args:
        key_id (uuid.UUID): The key to revoke.

    Raises:
        HTTPException: 403 when a scoped admin targets a key beyond its own scope.
    """
    # 1. A scoped caller may only revoke a key within its scope (an unknown key stays a no-op).
    target = await CONTEXT.database.auth.get_key(key_id)
    if (
        not principal.is_full_access
        and target is not None
        and not KeyGrantGuard.can_manage(principal, target.permissions)
    ):
        raise HTTPException(status_code=403, detail="API key is outside the caller's scope.")

    # 2. Stamp the revocation time (the facade no-ops on an unknown key), then drop this process's
    #    cached lookup so the key stops authenticating here at once rather than at the cache TTL.
    await CONTEXT.database.auth.revoke_key(key_id, datetime.now(UTC))
    if target is not None:
        evict_cached_key(target.key_hash)
    CONTEXT.logger.info(f"API key {key_id} revoked")


@router.post("/{key_id}/rotate", response_model=CreatedKey, status_code=201)
@auto_handle_errors
async def rotate_key(
    key_id: uuid.UUID,
    payload: RotateKeyRequest,
    principal: AuthPrincipal = Depends(require(Capability.ADMIN)),
) -> CreatedKey:
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
        HTTPException: 404 when the key is unknown or owned by another account; 403 when a scoped
            admin targets a key beyond its scope or re-scopes it beyond its own; 409 when it is
            already revoked (a terminal state — rotate an active key).
    """
    # 1. Resolve root and load the source key, refusing unknown or cross-tenant keys (404).
    root_id = await _require_root_id()
    old = await CONTEXT.database.auth.get_key(key_id)
    if old is None or old.user_id != root_id:
        raise HTTPException(status_code=404, detail="API key not found.")

    # 1b. A scoped caller may only rotate a key within its scope, into a scope within its own.
    if not KeyGrantGuard.can_manage(principal, old.permissions):
        raise HTTPException(status_code=403, detail="API key is outside the caller's scope.")
    if "permissions" in payload.model_fields_set:
        KeyGrantGuard.assert_can_grant(principal, payload.permissions)

    # 2. A revoked key is terminal — rotation applies only to an active key.
    if old.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Cannot rotate an already-revoked key.")

    # 3. Resolve the replacement fields (clone-from-source vs. override) and mint a fresh credential.
    #    A NEW scope is checked against the live store; a cloned one is kept as stored (a dangling
    #    alias in it simply grants nothing).
    if "permissions" in payload.model_fields_set:
        await KeyScopeAliases.validate_scope_entries(payload.permissions)
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

    # 4. Revoke the old key — the new secret is now the sole active credential. Evict its cached
    #    lookup so the rotated-away secret stops authenticating in THIS process at once (we already
    #    hold its hash; other replicas/the worker wait out the short TTL). The standalone DELETE
    #    /auth/keys/{id} path holds only the key id, so it relies on the TTL instead.
    await CONTEXT.database.auth.revoke_key(old.id, datetime.now(UTC))
    evict_cached_key(old.key_hash)
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
