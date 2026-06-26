# ====== Code Summary ======
# Unit tests for AuthService — resolve_principal (static root key | password JWT | scoped DB API
# key) and authenticate. All DB interactions are fully mocked (PostgresClient + repositories).
# No real DB or network. Per-collection authorization is no longer in AuthService — it is the
# capability scope carried on the resolved Principal (tested in test_auth_capabilities.py).

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.libs.auth.password import PasswordHelpers
from backend.libs.auth.service import AuthService
from backend.libs.auth.tokens import TokenHelpers
from common_libs.storage.postgres.models import UserRole

# ── Constants used across tests ────────────────────────────────────────────────

_ROOT_API_KEY = "static-root-api-key-for-tests"
_JWT_SECRET = "jwt-secret-for-tests"
_JWT_TTL = 60
_ROOT_USERNAME = "root"
_ROOT_PASSWORD = "root-password"


# ── Helper factories ────────────────────────────────────────────────────────────

def _make_user_orm(
    *,
    user_id: uuid.UUID | None = None,
    username: str = "alice",
    role: str = "user",
    is_active: bool = True,
    password_hash: str | None = None,
) -> MagicMock:
    """Build a minimal mock user ORM row."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.username = username
    user.role = role
    user.is_active = is_active
    user.password_hash = password_hash or PasswordHelpers.hash("default-password")
    return user


def _make_api_key_orm(
    *, owner_id: uuid.UUID, key_id: uuid.UUID | None = None, permissions: dict | None = None
) -> MagicMock:
    """Build a minimal mock API key ORM row, carrying an optional permissions scope."""
    key = MagicMock()
    key.id = key_id or uuid.uuid4()
    key.user_id = owner_id
    key.permissions = permissions
    return key


def _make_async_cm(return_value: object):
    """Return a callable that acts as an async context manager yielding return_value."""
    @asynccontextmanager
    async def _cm() -> AsyncIterator[object]:
        yield return_value

    return _cm


def _make_service(
    *,
    user_repo: MagicMock | None = None,
    api_key_repo: MagicMock | None = None,
    root_api_key: str = _ROOT_API_KEY,
) -> tuple[AuthService, MagicMock, MagicMock, MagicMock]:
    """
    Construct an AuthService with mock collaborators.

    Returns:
        tuple: (auth_service, mock_postgres, mock_user_repo, mock_api_key_repo)
    """
    mock_session = AsyncMock()
    mock_postgres = MagicMock()
    mock_postgres.session = _make_async_cm(mock_session)

    if user_repo is None:
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=None)
        user_repo.get_by_username = AsyncMock(return_value=None)

    if api_key_repo is None:
        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=None)
        api_key_repo.touch_last_used = AsyncMock()

    service = AuthService(
        postgres=mock_postgres,
        user_repo=user_repo,
        api_key_repo=api_key_repo,
        root_api_key=root_api_key,
        jwt_secret=_JWT_SECRET,
        jwt_ttl_minutes=_JWT_TTL,
        root_username=_ROOT_USERNAME,
        root_password=_ROOT_PASSWORD,
    )
    return service, mock_postgres, user_repo, api_key_repo


# ── resolve_principal ───────────────────────────────────────────────────────────

class TestResolvePrincipal:
    """Tests for AuthService.resolve_principal()."""

    @pytest.mark.asyncio
    async def test_none_bearer_returns_none(self) -> None:
        """No credential supplied → None (caller must raise 401)."""
        service, _, _, _ = _make_service()
        assert await service.resolve_principal(None) is None

    @pytest.mark.asyncio
    async def test_empty_bearer_returns_none(self) -> None:
        """Empty string credential → None."""
        service, _, _, _ = _make_service()
        assert await service.resolve_principal("") is None

    @pytest.mark.asyncio
    async def test_garbage_bearer_returns_none(self) -> None:
        """A completely invalid credential that is neither JWT nor DB key → None."""
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=None)
        user_repo.get_by_username = AsyncMock(return_value=None)
        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=None)
        api_key_repo.touch_last_used = AsyncMock()
        service, _, _, _ = _make_service(user_repo=user_repo, api_key_repo=api_key_repo)
        assert await service.resolve_principal("garbage-not-a-jwt-or-key") is None

    @pytest.mark.asyncio
    async def test_static_root_key_resolves_to_full_access_root(self) -> None:
        """The static root API key resolves to a full-access root principal (after bootstrap)."""
        root_user = _make_user_orm(user_id=uuid.uuid4(), username=_ROOT_USERNAME, role="root")
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=root_user)
        user_repo.upsert_root = AsyncMock(return_value=root_user)
        service, _, _, _ = _make_service(user_repo=user_repo)
        await service.bootstrap_root()

        result = await service.resolve_principal(_ROOT_API_KEY)

        assert result is not None
        assert result.is_root is True
        assert result.username == _ROOT_USERNAME
        assert result.global_role == UserRole.ROOT
        # Static root key → unscoped (full access)
        assert result.permissions is None
        assert result.has_full_access is True

    @pytest.mark.asyncio
    async def test_static_root_key_fails_when_not_bootstrapped(self) -> None:
        """Root API key is correct but bootstrap never ran → None (fail-closed)."""
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _ = _make_service(user_repo=user_repo)
        assert await service.resolve_principal(_ROOT_API_KEY) is None

    @pytest.mark.asyncio
    async def test_valid_jwt_resolves_to_full_access_user(self) -> None:
        """A valid password JWT resolves to a full-access principal (login is root-only)."""
        user_id = uuid.uuid4()
        user = _make_user_orm(user_id=user_id, username="root", role="root")
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _ = _make_service(user_repo=user_repo)

        token = TokenHelpers.mint(subject=str(user_id), secret=_JWT_SECRET, ttl_minutes=_JWT_TTL)
        result = await service.resolve_principal(token)

        assert result is not None
        assert result.user_id == user_id
        assert result.permissions is None  # login JWT carries no key scope → full access

    @pytest.mark.asyncio
    async def test_jwt_with_inactive_user_returns_none(self) -> None:
        """A valid JWT whose subject is an inactive user → None."""
        user_id = uuid.uuid4()
        inactive_user = _make_user_orm(user_id=user_id, is_active=False)
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=inactive_user)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _ = _make_service(user_repo=user_repo)

        token = TokenHelpers.mint(subject=str(user_id), secret=_JWT_SECRET, ttl_minutes=_JWT_TTL)
        assert await service.resolve_principal(token) is None

    @pytest.mark.asyncio
    async def test_scoped_db_api_key_carries_permissions(self) -> None:
        """A DB API key with a permissions scope resolves to a principal carrying that scope."""
        owner_id = uuid.uuid4()
        owner = _make_user_orm(user_id=owner_id, username="root", role="root")
        perms = {"entries": [{"collection_id": "*", "role": "read"}]}
        api_key = _make_api_key_orm(owner_id=owner_id, permissions=perms)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=owner)
        user_repo.get_by_username = AsyncMock(return_value=None)
        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=api_key)
        api_key_repo.touch_last_used = AsyncMock()
        service, _, _, _ = _make_service(user_repo=user_repo, api_key_repo=api_key_repo)

        result = await service.resolve_principal("some-valid-db-key")

        assert result is not None
        assert result.permissions == perms
        assert result.has_full_access is False
        api_key_repo.touch_last_used.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_null_permission_db_api_key_is_full_access(self) -> None:
        """A DB API key with NULL permissions resolves to a full-access principal (back-compat)."""
        owner_id = uuid.uuid4()
        owner = _make_user_orm(user_id=owner_id, username="root", role="root")
        api_key = _make_api_key_orm(owner_id=owner_id, permissions=None)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=owner)
        user_repo.get_by_username = AsyncMock(return_value=None)
        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=api_key)
        api_key_repo.touch_last_used = AsyncMock()
        service, _, _, _ = _make_service(user_repo=user_repo, api_key_repo=api_key_repo)

        result = await service.resolve_principal("legacy-null-key")

        assert result is not None
        assert result.permissions is None
        assert result.has_full_access is True


# ── authenticate ────────────────────────────────────────────────────────────────

class TestAuthenticate:
    """Tests for AuthService.authenticate() — username/password login path."""

    @pytest.mark.asyncio
    async def test_correct_credentials_return_principal(self) -> None:
        """Valid username + correct password → Principal (full access)."""
        password = "correct-password"
        user_id = uuid.uuid4()
        user = _make_user_orm(
            user_id=user_id, username="root", role="root",
            password_hash=PasswordHelpers.hash(password),
        )
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=user)
        service, _, _, _ = _make_service(user_repo=user_repo)

        principal = await service.authenticate("root", password)

        assert principal is not None
        assert principal.user_id == user_id
        assert principal.permissions is None

    @pytest.mark.asyncio
    async def test_wrong_password_returns_none(self) -> None:
        """Correct username but wrong password → None."""
        user = _make_user_orm(password_hash=PasswordHelpers.hash("correct-password"))
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=user)
        service, _, _, _ = _make_service(user_repo=user_repo)
        assert await service.authenticate(user.username, "wrong-password") is None

    @pytest.mark.asyncio
    async def test_unknown_username_returns_none(self) -> None:
        """Unknown username → None (user does not exist)."""
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _ = _make_service(user_repo=user_repo)
        assert await service.authenticate("ghost", "any-password") is None

    @pytest.mark.asyncio
    async def test_inactive_user_returns_none(self) -> None:
        """Correct credentials for a deactivated account → None."""
        password = "correct-password"
        inactive_user = _make_user_orm(
            is_active=False, password_hash=PasswordHelpers.hash(password)
        )
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=inactive_user)
        service, _, _, _ = _make_service(user_repo=user_repo)
        assert await service.authenticate(inactive_user.username, password) is None
