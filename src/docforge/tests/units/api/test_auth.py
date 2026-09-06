"""API-key auth (Lot 4): key generation/hashing (AuthKeys), the authN gate (authenticate — bearer
token -> AuthPrincipal, uniform 401 on any credential failure), the authZ gate (AuthzGuard.enforce /
require — capability + path-scoped collection check on top of the authenticated principal), and the
KeyPermissions scope model (extra="forbid" + the collections validator). All store access is mocked
via CONTEXT.database.auth; ``from backend...``/``from config...`` imports are deferred until the
``fastapi_app`` fixture has registered app/ on sys.path.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

# ── shared fakes ──────────────────────────────────────────────────────────────────────────────


def _request(
    headers: dict | None = None, path_params: dict | None = None, principal=None
) -> SimpleNamespace:
    """A minimal stand-in for a Starlette Request — only .headers/.path_params/.state are touched.

    ``principal`` seeds ``request.state.principal`` the way the authN middleware does, so the
    ``require`` dependency (which reads it there) can be exercised in isolation.
    """
    return SimpleNamespace(
        headers=headers or {},
        path_params=path_params or {},
        state=SimpleNamespace(principal=principal),
    )


def _key(
    *,
    permissions=None,
    revoked_at=None,
    user_id="user-1",
    key_id="key-1",
    expires_at=None,
    last_used_at=None,
) -> SimpleNamespace:
    """A mutable stand-in for an ApiKey row (only the fields the auth code touches)."""
    return SimpleNamespace(
        id=key_id,
        permissions=permissions,
        revoked_at=revoked_at,
        user_id=user_id,
        expires_at=expires_at,
        last_used_at=last_used_at,
    )


def _user(*, is_active: bool = True) -> SimpleNamespace:
    """A mutable stand-in for an AppUser row (only the fields the auth code touches)."""
    return SimpleNamespace(is_active=is_active)


def _principal(*, permissions, is_active: bool = True):
    """Build an AuthPrincipal directly, bypassing from_key, for authz-only tests."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    return AuthPrincipal(
        user=_user(is_active=is_active),
        key=_key(permissions=permissions),
        is_full_access=permissions is None,
    )


# ── AuthKeys ──────────────────────────────────────────────────────────────────────────────────


def test_hash_key_is_deterministic_sha256(fastapi_app) -> None:
    from backend.libs.auth.keys import AuthKeys  # noqa: PLC0415

    plaintext = "df_some-plaintext-key"
    assert AuthKeys.hash_key(plaintext) == AuthKeys.hash_key(plaintext)
    assert AuthKeys.hash_key(plaintext) == hashlib.sha256(plaintext.encode()).hexdigest()


def test_generate_key_shape(fastapi_app) -> None:
    from backend.libs.auth.keys import AuthKeys  # noqa: PLC0415

    plaintext, prefix, key_hash = AuthKeys.generate_key()

    assert plaintext.startswith("df_")
    assert len(prefix) == 12
    assert prefix == plaintext[:12]
    assert key_hash == AuthKeys.hash_key(plaintext)


def test_generate_key_two_calls_differ(fastapi_app) -> None:
    from backend.libs.auth.keys import AuthKeys  # noqa: PLC0415

    first_plaintext, _, first_hash = AuthKeys.generate_key()
    second_plaintext, _, second_hash = AuthKeys.generate_key()

    assert first_plaintext != second_plaintext
    assert first_hash != second_hash


def test_auth_keys_is_static_only(fastapi_app) -> None:
    from backend.libs.auth.keys import AuthKeys  # noqa: PLC0415

    with pytest.raises(TypeError):
        AuthKeys()


# ── authenticate ──────────────────────────────────────────────────────────────────────────────


async def test_authenticate_auth_off_returns_synthetic_root(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False)
    # `get_key_with_user` is the ACTUAL method `authenticate` calls on the enabled path (see
    # dependency.py step 3) — asserting non-invocation on it (rather than an unrelated method
    # name like `get_key_by_hash`, which is never called from `authenticate` in ANY path and so
    # would pass vacuously regardless of the AUTH_ENABLED short-circuit) proves the disabled path
    # truly never reaches the DB.
    auth = SimpleNamespace(get_key_with_user=AsyncMock(), touch_key_last_used=AsyncMock())
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    principal = await authenticate(_request())

    assert principal.is_full_access is True
    assert principal.key is None
    assert principal.user is None
    auth.get_key_with_user.assert_not_called()
    auth.touch_key_last_used.assert_not_called()


async def test_authenticate_missing_header_is_401(fastapi_app, monkeypatch) -> None:
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request())

    assert exc.value.status_code == 401
    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


async def test_authenticate_malformed_scheme_is_401(fastapi_app, monkeypatch) -> None:
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Token abc123"}))

    assert exc.value.status_code == 401


async def test_authenticate_empty_bearer_token_is_401(fastapi_app, monkeypatch) -> None:
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Bearer "}))

    assert exc.value.status_code == 401


async def test_authenticate_unknown_key_is_401(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    auth = SimpleNamespace(get_key_with_user=AsyncMock(return_value=None))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert exc.value.status_code == 401


async def test_authenticate_revoked_key_is_401(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    revoked_key = _key(revoked_at="2026-01-01T00:00:00Z")
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(revoked_key, _user(is_active=True)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert exc.value.status_code == 401


async def test_authenticate_inactive_owner_is_401(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    active_key = _key()
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(active_key, _user(is_active=False)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert exc.value.status_code == 401


async def test_authenticate_missing_owner_is_401(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    # The inner join collapses a missing owner row to None — the same opaque 401 as an unknown key.
    auth = SimpleNamespace(get_key_with_user=AsyncMock(return_value=None))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert exc.value.status_code == 401


async def test_authenticate_valid_full_access_key_returns_principal(
    fastapi_app, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from backend.libs.auth.keys import AuthKeys  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    plaintext, _, key_hash = AuthKeys.generate_key()
    full_access_key = _key(permissions=None)
    owner = _user(is_active=True)
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(full_access_key, owner)),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    principal = await authenticate(_request(headers={"Authorization": f"Bearer {plaintext}"}))

    assert principal.key is full_access_key
    assert principal.user is owner
    assert principal.is_full_access is True
    auth.get_key_with_user.assert_awaited_once_with(key_hash)


async def test_authenticate_valid_scoped_key_is_not_full_access(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    scoped_key = _key(permissions={"capabilities": ["read"], "collections": ["*"]})
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(scoped_key, _user(is_active=True))),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    principal = await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert principal.is_full_access is False
    assert principal.key is scoped_key


def _frozen_now(monkeypatch, instant) -> None:
    """Pin ``dependency.datetime.now`` to a fixed instant for deterministic expiry/touch assertions.

    Only ``datetime.now`` is redirected; ``UTC``/``timedelta`` stay real, and every comparison in
    ``authenticate``/``_is_last_used_stale`` runs against the single ``now`` this returns.
    """
    from backend.libs.auth import dependency as dep  # noqa: PLC0415

    class _FrozenDatetime(dep.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001 — mirrors datetime.now's signature
            return instant

    monkeypatch.setattr(dep, "datetime", _FrozenDatetime)


async def test_authenticate_expired_key_is_401_with_opaque_message(
    fastapi_app, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import _INVALID_CREDENTIAL, authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    fixed_now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
    _frozen_now(monkeypatch, fixed_now)
    expired_key = _key(expires_at=fixed_now - timedelta(seconds=1))
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(expired_key, _user(is_active=True)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    with pytest.raises(HTTPException) as exc:
        await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    # Same opaque message as the revoked-key case (test_authenticate_revoked_key_is_401) — an
    # expired key must be indistinguishable from a revoked one to the caller.
    assert exc.value.status_code == 401
    assert exc.value.detail == _INVALID_CREDENTIAL


async def test_authenticate_future_expiry_key_authenticates(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    fixed_now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
    _frozen_now(monkeypatch, fixed_now)
    future_key = _key(expires_at=fixed_now + timedelta(days=1))
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(future_key, _user(is_active=True)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    principal = await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert principal.key is future_key


async def test_authenticate_null_expiry_key_never_expires(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    never_expiring_key = _key(expires_at=None)
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(never_expiring_key, _user(is_active=True)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    principal = await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert principal.key is never_expiring_key


async def test_authenticate_touches_last_used_when_never_used(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    fixed_now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
    _frozen_now(monkeypatch, fixed_now)
    key = _key(last_used_at=None, key_id="key-never-used")
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(key, _user(is_active=True))),
        touch_key_last_used=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    auth.touch_key_last_used.assert_awaited_once_with(key.id, fixed_now)


async def test_authenticate_touches_last_used_when_stale(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    fixed_now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
    _frozen_now(monkeypatch, fixed_now)
    key = _key(last_used_at=fixed_now - timedelta(seconds=61), key_id="key-stale")
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(key, _user(is_active=True))),
        touch_key_last_used=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    auth.touch_key_last_used.assert_awaited_once_with(key.id, fixed_now)


async def test_authenticate_skips_last_used_touch_when_fresh(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    fixed_now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
    _frozen_now(monkeypatch, fixed_now)
    key = _key(last_used_at=fixed_now - timedelta(seconds=30), key_id="key-fresh")
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(key, _user(is_active=True))),
        touch_key_last_used=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    auth.touch_key_last_used.assert_not_called()


async def test_authenticate_swallows_last_used_touch_failure(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    key = _key(last_used_at=None)
    auth = SimpleNamespace(
        get_key_with_user=AsyncMock(return_value=(key, _user(is_active=True))),
        touch_key_last_used=AsyncMock(side_effect=RuntimeError("db unreachable")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    # A metrics-write failure must never turn a valid request into a 500 — the principal still comes back.
    principal = await authenticate(_request(headers={"Authorization": "Bearer df_whatever"}))

    assert principal.key is key
    auth.touch_key_last_used.assert_awaited_once()


async def test_authenticate_auth_off_never_touches_last_used(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import authenticate  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False)
    auth = SimpleNamespace(get_key_with_user=AsyncMock(), touch_key_last_used=AsyncMock())
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await authenticate(_request())

    auth.get_key_with_user.assert_not_called()
    auth.touch_key_last_used.assert_not_called()


# ── AuthzGuard.enforce / require ─────────────────────────────────────────────────────────────


def test_enforce_full_access_bypasses_capability_and_collection(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    principal = _principal(permissions=None)
    request = _request(path_params={"collection_id": "any-collection-not-scoped"})

    result = AuthzGuard.enforce(Capability.ADMIN, principal, request)

    assert result is principal


def test_enforce_scoped_key_missing_capability_is_403(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    principal = _principal(permissions={"capabilities": ["read"], "collections": ["*"]})

    with pytest.raises(HTTPException) as exc:
        AuthzGuard.enforce(Capability.WRITE, principal, _request())

    assert exc.value.status_code == 403


def test_enforce_scoped_key_wrong_collection_is_403(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    scoped_collection = "11111111-1111-1111-1111-111111111111"
    other_collection = "22222222-2222-2222-2222-222222222222"
    principal = _principal(
        permissions={"capabilities": ["read"], "collections": [scoped_collection]}
    )
    request = _request(path_params={"collection_id": other_collection})

    with pytest.raises(HTTPException) as exc:
        AuthzGuard.enforce(Capability.READ, principal, request)

    assert exc.value.status_code == 403


def test_enforce_scoped_key_matching_collection_is_allowed(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    collection_id = "11111111-1111-1111-1111-111111111111"
    principal = _principal(permissions={"capabilities": ["read"], "collections": [collection_id]})
    request = _request(path_params={"collection_id": collection_id})

    result = AuthzGuard.enforce(Capability.READ, principal, request)

    assert result is principal


def test_enforce_scoped_key_wildcard_collection_is_allowed(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    principal = _principal(permissions={"capabilities": ["read"], "collections": ["*"]})
    request = _request(path_params={"collection_id": "any-uuid-string"})

    result = AuthzGuard.enforce(Capability.READ, principal, request)

    assert result is principal


def test_enforce_scoped_key_without_collection_path_param_skips_scope_check(fastapi_app) -> None:
    """No collection_id path param (e.g. a document_id-keyed route) — capability alone gates it."""
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    principal = _principal(
        permissions={
            "capabilities": ["read"],
            "collections": ["11111111-1111-1111-1111-111111111111"],
        }
    )

    result = AuthzGuard.enforce(Capability.READ, principal, _request())

    assert result is principal


def test_enforce_malformed_permissions_blob_is_403(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    # Missing the required "collections" key — fails KeyPermissions.model_validate.
    principal = _principal(permissions={"capabilities": ["read"]})

    with pytest.raises(HTTPException) as exc:
        AuthzGuard.enforce(Capability.READ, principal, _request())

    assert exc.value.status_code == 403


async def test_require_builds_a_working_dependency(fastapi_app) -> None:
    from backend.libs.auth.authz import require  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    principal = _principal(permissions={"capabilities": ["search"], "collections": ["*"]})
    dependency = require(Capability.SEARCH)

    result = await dependency(_request(principal=principal))

    assert result is principal


async def test_require_denies_when_capability_absent(fastapi_app) -> None:
    from backend.libs.auth.authz import require  # noqa: PLC0415
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    principal = _principal(permissions={"capabilities": ["search"], "collections": ["*"]})
    dependency = require(Capability.ADMIN)

    with pytest.raises(HTTPException) as exc:
        await dependency(_request(principal=principal))

    assert exc.value.status_code == 403


# ── KeyPermissions ────────────────────────────────────────────────────────────────────────────


def test_key_permissions_valid_parse(fastapi_app) -> None:
    from backend.libs.auth.permissions import Capability, KeyPermissions  # noqa: PLC0415

    permissions = KeyPermissions.model_validate(
        {"capabilities": ["read", "write"], "collections": ["*"]}
    )

    assert permissions.capabilities == [Capability.READ, Capability.WRITE]
    assert permissions.collections == ["*"]


def test_key_permissions_extra_field_is_rejected(fastapi_app) -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from backend.libs.auth.permissions import KeyPermissions  # noqa: PLC0415

    with pytest.raises(ValidationError):
        KeyPermissions.model_validate(
            {"capabilities": ["read"], "collections": ["*"], "bogus_field": True}
        )


def test_key_permissions_wildcard_alone_is_valid(fastapi_app) -> None:
    from backend.libs.auth.permissions import KeyPermissions  # noqa: PLC0415

    permissions = KeyPermissions.model_validate({"capabilities": [], "collections": ["*"]})

    assert permissions.collections == ["*"]


def test_key_permissions_wildcard_mixed_with_explicit_ids_is_rejected(fastapi_app) -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from backend.libs.auth.permissions import KeyPermissions  # noqa: PLC0415

    with pytest.raises(ValidationError):
        KeyPermissions.model_validate(
            {
                "capabilities": [],
                "collections": ["*", "11111111-1111-1111-1111-111111111111"],
            }
        )


def test_key_permissions_explicit_uuid_list_is_valid(fastapi_app) -> None:
    from backend.libs.auth.permissions import KeyPermissions  # noqa: PLC0415

    collection_id = "11111111-1111-1111-1111-111111111111"
    permissions = KeyPermissions.model_validate(
        {"capabilities": [], "collections": [collection_id]}
    )

    assert permissions.collections == [collection_id]


def test_key_permissions_non_uuid_entry_is_rejected(fastapi_app) -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from backend.libs.auth.permissions import KeyPermissions  # noqa: PLC0415

    with pytest.raises(ValidationError):
        KeyPermissions.model_validate({"capabilities": [], "collections": ["not-a-uuid"]})


def test_key_permissions_grants_capability_and_collection(fastapi_app) -> None:
    from backend.libs.auth.permissions import Capability, KeyPermissions  # noqa: PLC0415

    collection_id = "11111111-1111-1111-1111-111111111111"
    permissions = KeyPermissions.model_validate(
        {"capabilities": ["read"], "collections": [collection_id]}
    )

    assert permissions.grants_capability(Capability.READ) is True
    assert permissions.grants_capability(Capability.WRITE) is False
    assert permissions.grants_collection(collection_id) is True
    assert permissions.grants_collection("22222222-2222-2222-2222-222222222222") is False


# ── AuthMiddleware (pure ASGI authN gate) ───────────────────────────────────────────────────────


def _asgi_http_scope(path: str) -> dict:
    """A minimal ASGI HTTP scope carrying just the fields the middleware reads."""
    return {"type": "http", "path": path, "headers": []}


async def _drain(*_args, **_kwargs) -> dict:
    """A no-op ASGI receive channel (the middleware never pulls the body itself)."""
    return {"type": "http.request", "body": b"", "more_body": False}


class _SendRecorder:
    """Captures the ASGI messages a short-circuit response sends back to the client."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for message in self.messages:
            if message["type"] == "http.response.start":
                return message["status"]
        return None


async def test_middleware_passes_non_http_scope_through(fastapi_app) -> None:
    from backend.libs.auth.middleware import AuthMiddleware  # noqa: PLC0415

    called = {"downstream": False}

    async def downstream(scope, receive, send) -> None:
        called["downstream"] = True

    await AuthMiddleware(downstream)({"type": "websocket"}, _drain, _SendRecorder())

    assert called["downstream"] is True


async def test_middleware_passes_public_path_through_without_auth(fastapi_app) -> None:
    from backend.libs.auth.middleware import AuthMiddleware  # noqa: PLC0415

    seen = {"scope": None}

    async def downstream(scope, receive, send) -> None:
        seen["scope"] = scope

    await AuthMiddleware(downstream)(_asgi_http_scope("/scalar"), _drain, _SendRecorder())

    # Public paths never get a principal injected — they were not authenticated.
    assert seen["scope"] is not None
    assert "principal" not in seen["scope"].get("state", {})


async def test_middleware_injects_synthetic_principal_when_auth_off(
    fastapi_app, monkeypatch
) -> None:
    from backend.libs.auth import dependency as dep  # noqa: PLC0415
    from backend.libs.auth.middleware import AuthMiddleware  # noqa: PLC0415

    monkeypatch.setattr(dep.RUNTIME_CONFIG, "AUTH_ENABLED", False)
    seen = {"scope": None}

    async def downstream(scope, receive, send) -> None:
        seen["scope"] = scope

    await AuthMiddleware(downstream)(
        _asgi_http_scope("/api/v1/collections"), _drain, _SendRecorder()
    )

    principal = seen["scope"]["state"]["principal"]
    assert principal.is_full_access is True


async def test_middleware_short_circuits_401_before_downstream(fastapi_app, monkeypatch) -> None:
    from backend.libs.auth import dependency as dep  # noqa: PLC0415
    from backend.libs.auth.middleware import AuthMiddleware  # noqa: PLC0415

    monkeypatch.setattr(dep.RUNTIME_CONFIG, "AUTH_ENABLED", True)
    called = {"downstream": False}

    async def downstream(scope, receive, send) -> None:
        called["downstream"] = True

    recorder = _SendRecorder()
    # No Authorization header on a gated path → 401, and the wrapped app is never reached.
    await AuthMiddleware(downstream)(_asgi_http_scope("/api/v1/collections"), _drain, recorder)

    assert recorder.status == 401
    assert called["downstream"] is False


# ── whoami self-introspection (GET /auth/whoami) ────────────────────────────────────────────────


async def test_whoami_reports_full_access_for_a_root_principal(fastapi_app) -> None:
    from backend.libs.auth import Capability  # noqa: PLC0415
    from backend.routers.auth.whoami import whoami  # noqa: PLC0415

    # A null-permissions / auth-off principal is full-access: every capability, wildcard scope.
    result = await whoami(principal=_principal(permissions=None))
    assert result.root is True
    assert result.collections == ["*"]
    assert set(result.capabilities) == {c.value for c in Capability}


async def test_whoami_reports_a_scoped_keys_grants(fastapi_app) -> None:
    from backend.routers.auth.whoami import whoami  # noqa: PLC0415

    collection_id = "11111111-1111-1111-1111-111111111111"
    result = await whoami(
        principal=_principal(permissions={"capabilities": ["read"], "collections": [collection_id]})
    )
    assert result.root is False
    assert result.capabilities == ["read"]
    assert result.collections == [collection_id]


async def test_whoami_degrades_to_403_on_a_malformed_permissions_blob(fastapi_app) -> None:
    from backend.routers.auth.whoami import whoami  # noqa: PLC0415

    # A corrupt/legacy blob (extra='forbid' rejects the unknown field) must DEGRADE like the authz
    # gate — a clean 403, never an unhandled ValidationError surfaced as a 500 by auto_handle_errors.
    with pytest.raises(HTTPException) as excinfo:
        await whoami(principal=_principal(permissions={"garbage_field": True}))
    assert excinfo.value.status_code == 403
