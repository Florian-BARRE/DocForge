"""Collection aliases (G1): the alias-name grammar, the `{collection_id}` ref resolver (UUID or alias,
unknown → 404), a key scoped `alias:<name>` following a re-point on the very next request and failing
closed once the alias is gone, the alias write route (422 / 409 clash / 201 create / 200 re-point), the
alias↔collection-name collision both ways, the collection DELETE refused while aliased (409), the
key-write existence check, and the audit attribution of alias routes.

``from backend...`` imports are deferred until the ``fastapi_app`` fixture registered app/ on sys.path.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
HEADERS = {"Authorization": "Bearer df_alias"}


def _live_targets(monkeypatch, targets: dict[str, uuid.UUID]) -> AsyncMock:
    """Back `collection_aliases.targets_of` with a MUTABLE map (a re-point = a dict update)."""
    from backend.context import CONTEXT  # noqa: PLC0415

    lookup = AsyncMock(side_effect=lambda names: {n: targets[n] for n in names if n in targets})
    monkeypatch.setattr(CONTEXT.database.collection_aliases, "targets_of", lookup)
    return lookup


def _scoped_key(monkeypatch, collections: list[str]) -> None:
    """Auth ON with one scoped read key (cache bypassed so every request re-authenticates)."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import _KEY_CACHE  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    key = SimpleNamespace(
        id=uuid.uuid4(),
        permissions={"capabilities": ["read"], "collections": collections},
        revoked_at=None,
        user_id=uuid.uuid4(),
        expires_at=None,
        last_used_at=None,
    )
    auth = CONTEXT.database.auth
    monkeypatch.setattr(
        auth, "get_key_with_user", AsyncMock(return_value=(key, SimpleNamespace(is_active=True)))
    )
    monkeypatch.setattr(auth, "touch_key_last_used", AsyncMock())
    monkeypatch.setattr(_KEY_CACHE, "get", lambda _hash: (False, None))


def _unknown_collections(monkeypatch) -> AsyncMock:
    """Make every collection lookup miss: a 404 from the handler proves authZ let the call through."""
    from backend.context import CONTEXT  # noqa: PLC0415

    get = AsyncMock(return_value=None)
    monkeypatch.setattr(CONTEXT.database.collections, "get", get)
    return get


# ── grammar ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["chatmop", "chat-mop_2", "0x"])
def test_valid_alias_names(fastapi_app, name) -> None:
    from backend.libs.collection_ref import CollectionAliasName  # noqa: PLC0415

    assert CollectionAliasName.problem(name) is None


@pytest.mark.parametrize("name", ["Chatmop", "-x", "a b", "", "x" * 64, str(A), "import"])
def test_invalid_alias_names(fastapi_app, name) -> None:
    from backend.libs.collection_ref import CollectionAliasName  # noqa: PLC0415

    assert CollectionAliasName.problem(name) is not None


def test_key_scope_grammar_and_fail_closed_resolution(fastapi_app) -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from backend.libs.auth import KeyPermissions  # noqa: PLC0415

    scope = KeyPermissions.model_validate(
        {"capabilities": ["read"], "collections": [str(A), "alias:chatmop", "alias:gone"]}
    )
    assert scope.alias_names() == ["chatmop", "gone"]
    effective = scope.with_resolved_aliases({"chatmop": str(B)})
    assert effective.collections == [str(A), str(B)]
    with pytest.raises(ValidationError):
        KeyPermissions.model_validate({"capabilities": ["read"], "collections": ["alias:Bad"]})


# ── ref resolution on collection routes ───────────────────────────────────────────────────────────


def test_alias_ref_resolves_to_its_target(client, monkeypatch) -> None:
    _live_targets(monkeypatch, {"chatmop": A})
    get = _unknown_collections(monkeypatch)

    assert client.get("/api/v1/collections/chatmop").status_code == 404
    get.assert_awaited_with(A)


def test_unknown_or_malformed_ref_is_a_404_without_lookup_for_malformed(
    client, monkeypatch
) -> None:
    lookup = _live_targets(monkeypatch, {})
    _unknown_collections(monkeypatch)

    response = client.get("/api/v1/collections/nope")
    assert response.status_code == 404 and "nope" in response.json()["detail"]
    lookup.reset_mock()
    assert client.get("/api/v1/collections/NOT_A_SLUG").status_code == 404
    lookup.assert_not_awaited()


def test_query_ref_on_job_routes_resolves_an_alias(client, monkeypatch) -> None:
    _live_targets(monkeypatch, {"chatmop": A})
    missing = client.get("/api/v1/jobs", params={"collection_id": "missing"})
    assert missing.status_code == 404 and "missing" in missing.json()["detail"]


async def test_query_ref_dependency_returns_the_target(fastapi_app, monkeypatch) -> None:
    from starlette.requests import Request  # noqa: PLC0415

    from backend.libs.collection_ref import CollectionRefResolver  # noqa: PLC0415

    _live_targets(monkeypatch, {"chatmop": A})
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    assert await CollectionRefResolver.from_query(request, "chatmop") == A
    assert await CollectionRefResolver.from_optional_query(request, None) is None
    assert await CollectionRefResolver.from_query(request, str(B)) == B


# ── key scope `alias:<name>` ─────────────────────────────────────────────────────────────────────


def test_alias_scoped_key_follows_a_repoint(client, monkeypatch) -> None:
    targets = {"chatmop": A}
    _live_targets(monkeypatch, targets)
    _scoped_key(monkeypatch, ["alias:chatmop"])
    _unknown_collections(monkeypatch)

    assert client.get(f"/api/v1/collections/{A}", headers=HEADERS).status_code == 404
    assert client.get(f"/api/v1/collections/{B}", headers=HEADERS).status_code == 403

    targets["chatmop"] = B  # the switch — no key edit, no cache flush
    assert client.get(f"/api/v1/collections/{A}", headers=HEADERS).status_code == 403
    assert client.get(f"/api/v1/collections/{B}", headers=HEADERS).status_code == 404
    assert client.get("/api/v1/collections/chatmop", headers=HEADERS).status_code == 404


def test_alias_scoped_key_fails_closed_once_the_alias_is_gone(client, monkeypatch) -> None:
    targets = {"chatmop": A}
    _live_targets(monkeypatch, targets)
    _scoped_key(monkeypatch, ["alias:chatmop"])
    _unknown_collections(monkeypatch)

    del targets["chatmop"]
    assert client.get(f"/api/v1/collections/{A}", headers=HEADERS).status_code == 403


async def test_key_write_refuses_an_unknown_alias(fastapi_app, monkeypatch) -> None:
    from backend.libs.auth import KeyPermissions, KeyScopeAliases  # noqa: PLC0415

    _live_targets(monkeypatch, {"chatmop": A})
    ok = KeyPermissions.model_validate({"capabilities": ["read"], "collections": ["alias:chatmop"]})
    await KeyScopeAliases.validate_scope_entries(ok)
    bad = KeyPermissions.model_validate({"capabilities": ["read"], "collections": ["alias:gone"]})
    with pytest.raises(HTTPException) as refused:
        await KeyScopeAliases.validate_scope_entries(bad)
    assert refused.value.status_code == 422 and "gone" in refused.value.detail


# ── alias writes + collisions ─────────────────────────────────────────────────────────────────────


def _write(previous: uuid.UUID | None, target: uuid.UUID = A):
    from shared_libs.services.db.facades import CollectionAliasWrite  # noqa: PLC0415

    now = datetime.now(UTC)
    return CollectionAliasWrite("chatmop", target, previous, now, now)


def _alias_store(monkeypatch, **methods) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

    for name, mock in methods.items():
        monkeypatch.setattr(CONTEXT.database.collection_aliases, name, mock)
    monkeypatch.setattr(
        CONTEXT.database.collections, "get", AsyncMock(return_value=SimpleNamespace(name="v2"))
    )


def test_put_alias_creates_then_repoints(client, monkeypatch) -> None:
    _alias_store(monkeypatch, set=AsyncMock(side_effect=[_write(None), _write(A, B)]))

    created = client.put("/api/v1/collection-aliases/chatmop", json={"collection_id": str(A)})
    assert created.status_code == 201 and created.json()["created"] is True
    moved = client.put("/api/v1/collection-aliases/chatmop", json={"collection_id": str(B)})
    assert moved.status_code == 200
    assert moved.json()["previous_collection_id"] == str(A)
    assert moved.json()["collection_id"] == str(B)


def test_put_alias_refusals(client, monkeypatch) -> None:
    from shared_libs.services.db.facades import (  # noqa: PLC0415
        CollectionAliasNameClashError,
        CollectionAliasTargetMissingError,
    )

    _alias_store(
        monkeypatch,
        set=AsyncMock(
            side_effect=[CollectionAliasNameClashError("chatmop", "ChatMop"),
                         CollectionAliasTargetMissingError(A)]
        ),
    )  # fmt: skip
    url = "/api/v1/collection-aliases/chatmop"
    assert client.put(url, json={"collection_id": str(A)}).status_code == 409
    assert client.put(url, json={"collection_id": str(A)}).status_code == 404
    bad = client.put("/api/v1/collection-aliases/Bad", json={"collection_id": str(A)})
    assert bad.status_code == 422


def test_delete_alias(client, monkeypatch) -> None:
    _alias_store(monkeypatch, delete=AsyncMock(side_effect=[True, False]))

    assert client.delete("/api/v1/collection-aliases/chatmop").status_code == 204
    assert client.delete("/api/v1/collection-aliases/chatmop").status_code == 404


async def test_collection_name_equal_to_an_alias_is_a_409(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.collections.name_guard import CollectionNameGuard  # noqa: PLC0415

    monkeypatch.setattr(CONTEXT.database.collections, "get_by_name", AsyncMock(return_value=None))
    monkeypatch.setattr(
        CONTEXT.database.collection_aliases, "name_is_alias", AsyncMock(return_value=True)
    )
    with pytest.raises(HTTPException) as refused:
        await CollectionNameGuard.assert_free("ChatMop")
    assert refused.value.status_code == 409 and "alias" in refused.value.detail


def test_delete_of_an_aliased_collection_is_a_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from shared_libs.services.db.facades import CollectionAliasedError  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "delete",
        AsyncMock(side_effect=CollectionAliasedError(A, ["chatmop"])),
    )
    response = client.delete(f"/api/v1/collections/{A}")
    assert response.status_code == 409 and "chatmop" in response.json()["detail"]


# ── audit attribution ────────────────────────────────────────────────────────────────────────────


def test_audit_targets_alias_routes_by_name(fastapi_app) -> None:
    from backend.libs.audit.target_parser import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse("/api/v1/collection-aliases/chatmop") == (
        "collection_alias",
        "chatmop",
    )
    assert AuditTargetParser.parse("/api/v1/collections/chatmop") == ("collection", None)
