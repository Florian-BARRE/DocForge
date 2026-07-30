"""AuthBootstrap.ensure_root_credential — the startup provisioner for the root user + root API
key. Called directly (lifespan does not run under TestClient); `CONTEXT.database.auth` is mocked.
No live store."""

from types import SimpleNamespace
from unittest.mock import AsyncMock


async def test_noop_when_auth_disabled(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT
    from backend.libs.auth.bootstrap import AuthBootstrap
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_TOKEN", "some-token")
    auth = SimpleNamespace(
        get_user_by_username=AsyncMock(),
        create_user=AsyncMock(),
        create_key=AsyncMock(),
        get_key_by_hash=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await AuthBootstrap.ensure_root_credential()

    auth.get_user_by_username.assert_not_called()
    auth.create_user.assert_not_called()
    auth.create_key.assert_not_called()


async def test_noop_when_root_token_empty(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT
    from backend.libs.auth.bootstrap import AuthBootstrap
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_TOKEN", "")
    auth = SimpleNamespace(
        get_user_by_username=AsyncMock(),
        create_user=AsyncMock(),
        create_key=AsyncMock(),
        get_key_by_hash=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await AuthBootstrap.ensure_root_credential()

    auth.get_user_by_username.assert_not_called()
    auth.create_user.assert_not_called()
    auth.create_key.assert_not_called()


async def test_idempotent_when_root_and_key_already_present(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT
    from backend.libs.auth.bootstrap import AuthBootstrap
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_TOKEN", "df_root-token")
    existing_root = SimpleNamespace(id="root-id")
    auth = SimpleNamespace(
        get_user_by_username=AsyncMock(return_value=existing_root),
        create_user=AsyncMock(),
        get_key_by_hash=AsyncMock(return_value=SimpleNamespace(id="key-id")),
        create_key=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await AuthBootstrap.ensure_root_credential()

    # Both the user and the key already existed — nothing is (re)created.
    auth.create_user.assert_not_called()
    auth.create_key.assert_not_called()


async def test_provisions_root_user_and_key_when_missing(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT
    from backend.libs.auth.bootstrap import AuthBootstrap
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_TOKEN", "df_root-token")
    created_root = SimpleNamespace(id="root-id")
    auth = SimpleNamespace(
        get_user_by_username=AsyncMock(return_value=None),
        create_user=AsyncMock(return_value=created_root),
        get_key_by_hash=AsyncMock(return_value=None),
        create_key=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    await AuthBootstrap.ensure_root_credential()

    auth.create_user.assert_awaited_once()
    auth.create_key.assert_awaited_once()
    created_key = auth.create_key.await_args.args[0]
    assert created_key.user_id == "root-id"
    assert created_key.permissions is None


async def test_store_unreachable_at_boot_is_swallowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT
    from backend.libs.auth.bootstrap import AuthBootstrap
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_TOKEN", "df_root-token")
    auth = SimpleNamespace(
        get_user_by_username=AsyncMock(side_effect=ConnectionError("store unreachable")),
        create_user=AsyncMock(),
        get_key_by_hash=AsyncMock(),
        create_key=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(auth=auth))

    # Best-effort: never raises, even though the very first store call failed.
    await AuthBootstrap.ensure_root_credential()
