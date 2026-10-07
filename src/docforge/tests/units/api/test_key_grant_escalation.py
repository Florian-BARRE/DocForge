"""H1 — no privilege escalation through key management. A SCOPED admin key cannot mint a
root-equivalent (permissions=null) or '*' key, cannot grant collections / aliases / capabilities beyond
its own, cannot list / rotate / revoke a key outside its scope, while a full-access caller still can.
Plus L3: the reserved author labels "root" / "anonymous" are refused as key names.

``from backend...`` imports are deferred until the ``fastapi_app`` fixture registered app/ on sys.path.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ROOT_ID = uuid.uuid4()


def _principal(permissions, alias_targets=None):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    if permissions is None:
        return AuthPrincipal(user=None, key=None, is_full_access=True)
    key = SimpleNamespace(id=uuid.uuid4(), permissions=permissions, name="scoped", prefix="df_s")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True),
        key=key,
        is_full_access=False,
        alias_targets=alias_targets or {},
    )


SCOPED_ADMIN = {"capabilities": ["admin", "read_text"], "collections": [A, "alias:chatmop"]}


def _perm(capabilities, collections):
    from backend.libs.auth import KeyPermissions  # noqa: PLC0415

    return KeyPermissions.model_validate({"capabilities": capabilities, "collections": collections})


def _stored_key(permissions):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=ROOT_ID,
        name="k",
        prefix="df_k",
        key_hash="h",
        permissions=permissions,
        created_at=datetime.now(UTC),
        expires_at=None,
        last_used_at=None,
        revoked_at=None,
    )


@pytest.fixture
def auth_store(fastapi_app, monkeypatch):
    from backend.context import CONTEXT  # noqa: PLC0415

    auth = CONTEXT.database.auth
    monkeypatch.setattr(
        auth, "get_user_by_username", AsyncMock(return_value=SimpleNamespace(id=ROOT_ID))
    )
    monkeypatch.setattr(auth, "create_key", AsyncMock(side_effect=lambda key: _stored_key(None)))
    monkeypatch.setattr(auth, "revoke_key", AsyncMock())
    monkeypatch.setattr(
        CONTEXT.database.collection_aliases,
        "targets_of",
        AsyncMock(side_effect=lambda names: {n: uuid.UUID(A) for n in names}),
    )
    return auth


# ── the pure subset rule ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "requested",
    [
        None,
        (["read_text"], ["*"]),
        (["read_text"], [B]),
        (["write"], [A]),
        (["read_text"], ["alias:other"]),
    ],
)
def test_scoped_admin_cannot_exceed_its_grant(fastapi_app, requested) -> None:
    from backend.libs.auth import KeyGrantGuard  # noqa: PLC0415

    scope = None if requested is None else _perm(*requested)
    with pytest.raises(HTTPException) as refused:
        KeyGrantGuard.assert_can_grant(_principal(SCOPED_ADMIN, {"chatmop": A}), scope)
    assert refused.value.status_code == 403


def test_scoped_admin_may_grant_a_subset(fastapi_app) -> None:
    from backend.libs.auth import KeyGrantGuard  # noqa: PLC0415

    caller = _principal(SCOPED_ADMIN, {"chatmop": A})
    KeyGrantGuard.assert_can_grant(caller, _perm(["read_text"], [A, "alias:chatmop"]))
    # A wildcard admin may grant '*' but never a capability it lacks.
    wildcard = _principal({"capabilities": ["admin", "search"], "collections": ["*"]})
    KeyGrantGuard.assert_can_grant(wildcard, _perm(["search"], ["*"]))
    with pytest.raises(HTTPException):
        KeyGrantGuard.assert_can_grant(wildcard, _perm(["write"], ["*"]))


def test_full_access_grants_anything(fastapi_app) -> None:
    from backend.libs.auth import KeyGrantGuard  # noqa: PLC0415

    KeyGrantGuard.assert_can_grant(_principal(None), None)
    assert KeyGrantGuard.can_manage(_principal(None), None) is True


# ── the routes ───────────────────────────────────────────────────────────────────────────────────


async def test_create_refuses_null_and_star_for_a_scoped_admin(auth_store) -> None:
    from backend.routers.auth.models import CreateKeyRequest  # noqa: PLC0415
    from backend.routers.auth.router import create_key  # noqa: PLC0415

    caller = _principal(SCOPED_ADMIN, {"chatmop": A})
    for permissions in (None, {"capabilities": ["read_text"], "collections": ["*"]}):
        with pytest.raises(HTTPException) as refused:
            await create_key(CreateKeyRequest(name="x", permissions=permissions), principal=caller)
        assert refused.value.status_code == 403
    auth_store.create_key.assert_not_awaited()

    # A full-access caller still mints a root-equivalent key.
    await create_key(CreateKeyRequest(name="x", permissions=None), principal=_principal(None))
    auth_store.create_key.assert_awaited_once()


async def test_list_hides_out_of_scope_keys(auth_store, monkeypatch) -> None:
    from backend.routers.auth.router import list_keys  # noqa: PLC0415

    keys = [
        _stored_key(None),
        _stored_key({"capabilities": ["read_text"], "collections": [B]}),
        _stored_key({"capabilities": ["read_text"], "collections": [A]}),
    ]
    monkeypatch.setattr(auth_store, "list_keys", AsyncMock(return_value=keys))

    scoped = await list_keys(principal=_principal(SCOPED_ADMIN, {"chatmop": A}))
    assert [k.id for k in scoped] == [str(keys[2].id)]
    assert len(await list_keys(principal=_principal(None))) == 3


async def test_rotate_and_revoke_refuse_out_of_scope_keys(auth_store, monkeypatch) -> None:
    from backend.routers.auth.models import RotateKeyRequest  # noqa: PLC0415
    from backend.routers.auth.router import revoke_key, rotate_key  # noqa: PLC0415

    foreign = _stored_key({"capabilities": ["read_text"], "collections": [B]})
    monkeypatch.setattr(auth_store, "get_key", AsyncMock(return_value=foreign))
    caller = _principal(SCOPED_ADMIN, {"chatmop": A})

    with pytest.raises(HTTPException) as rotated:
        await rotate_key(foreign.id, RotateKeyRequest(), principal=caller)
    with pytest.raises(HTTPException) as revoked:
        await revoke_key(foreign.id, principal=caller)
    assert rotated.value.status_code == revoked.value.status_code == 403
    auth_store.revoke_key.assert_not_awaited()

    # An in-scope key cannot be rotated INTO a broader scope either.
    own = _stored_key({"capabilities": ["read_text"], "collections": [A]})
    monkeypatch.setattr(auth_store, "get_key", AsyncMock(return_value=own))
    with pytest.raises(HTTPException):
        await rotate_key(own.id, RotateKeyRequest(permissions=None), principal=caller)

    # Full access still rotates and revokes the foreign key.
    monkeypatch.setattr(auth_store, "get_key", AsyncMock(return_value=foreign))
    await rotate_key(foreign.id, RotateKeyRequest(), principal=_principal(None))
    await revoke_key(foreign.id, principal=_principal(None))
    assert auth_store.revoke_key.await_count == 2


@pytest.mark.parametrize("name", ["root", "Anonymous", " ROOT "])
def test_reserved_key_names_are_refused(fastapi_app, name) -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from backend.routers.auth.models import CreateKeyRequest, RotateKeyRequest  # noqa: PLC0415

    with pytest.raises(ValidationError):
        CreateKeyRequest(name=name)
    with pytest.raises(ValidationError):
        RotateKeyRequest(name=name)
