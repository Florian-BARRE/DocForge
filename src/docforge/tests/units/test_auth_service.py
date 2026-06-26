# ====== Code Summary ======
# Unit tests for AuthService — resolve_principal, authenticate, effective_collection_role.
# All DB interactions are fully mocked (PostgresClient + repositories). No real DB or network.

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.libs.auth.models import Principal
from backend.libs.auth.password import PasswordHelpers
from backend.libs.auth.service import AuthService
from backend.libs.auth.tokens import TokenHelpers
from common_libs.storage.postgres.models import GrantRole, UserRole

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


def _make_api_key_orm(*, owner_id: uuid.UUID, key_id: uuid.UUID | None = None) -> MagicMock:
    """Build a minimal mock API key ORM row."""
    key = MagicMock()
    key.id = key_id or uuid.uuid4()
    key.user_id = owner_id
    return key


def _make_grant_orm(*, user_id: uuid.UUID, collection_id: uuid.UUID, role: str) -> MagicMock:
    """Build a minimal mock collection grant ORM row."""
    grant = MagicMock()
    grant.user_id = user_id
    grant.collection_id = collection_id
    grant.role = role
    return grant


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
    grant_repo: MagicMock | None = None,
    root_api_key: str = _ROOT_API_KEY,
) -> tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock]:
    """
    Construct an AuthService with mock collaborators.

    Returns:
        tuple: (auth_service, mock_postgres, mock_user_repo, mock_api_key_repo, mock_grant_repo)
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

    if grant_repo is None:
        grant_repo = MagicMock()
        grant_repo.get = AsyncMock(return_value=None)

    service = AuthService(
        postgres=mock_postgres,
        user_repo=user_repo,
        api_key_repo=api_key_repo,
        grant_repo=grant_repo,
        root_api_key=root_api_key,
        jwt_secret=_JWT_SECRET,
        jwt_ttl_minutes=_JWT_TTL,
        root_username=_ROOT_USERNAME,
        root_password=_ROOT_PASSWORD,
    )
    return service, mock_postgres, user_repo, api_key_repo, grant_repo


# ── resolve_principal ───────────────────────────────────────────────────────────

class TestResolvePrincipal:
    """Tests for AuthService.resolve_principal()."""

    @pytest.mark.asyncio
    async def test_none_bearer_returns_none(self) -> None:
        """No credential supplied → None (caller must raise 401)."""
        service, _, _, _, _ = _make_service()
        result = await service.resolve_principal(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_bearer_returns_none(self) -> None:
        """Empty string credential → None."""
        service, _, _, _, _ = _make_service()
        result = await service.resolve_principal("")
        assert result is None

    @pytest.mark.asyncio
    async def test_garbage_bearer_returns_none(self) -> None:
        """A completely invalid credential that is neither JWT nor DB key → None."""
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=None)
        user_repo.get_by_username = AsyncMock(return_value=None)
        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=None)
        api_key_repo.touch_last_used = AsyncMock()
        service, _, _, _, _ = _make_service(
            user_repo=user_repo,
            api_key_repo=api_key_repo,
        )
        result = await service.resolve_principal("garbage-not-a-jwt-or-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_static_root_key_resolves_to_root_principal(self) -> None:
        """The static root API key resolves to a root principal (after bootstrap)."""
        root_user = _make_user_orm(user_id=uuid.uuid4(), username=_ROOT_USERNAME, role="root")
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=root_user)
        # The static-root-key path resolves from the cache populated by bootstrap_root(); it never
        # hits the DB per request. Bootstrap must therefore run first (fail-closed otherwise).
        user_repo.upsert_root = AsyncMock(return_value=root_user)
        service, _, _, _, _ = _make_service(user_repo=user_repo)
        await service.bootstrap_root()

        result = await service.resolve_principal(_ROOT_API_KEY)

        assert result is not None
        assert result.is_root is True
        assert result.username == _ROOT_USERNAME
        assert result.global_role == UserRole.ROOT

    @pytest.mark.asyncio
    async def test_static_root_key_fails_when_root_account_missing(self) -> None:
        """Root API key is correct but the root account is absent in DB → None (fail-closed)."""
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        result = await service.resolve_principal(_ROOT_API_KEY)
        assert result is None

    @pytest.mark.asyncio
    async def test_static_root_key_fails_when_root_account_inactive(self) -> None:
        """Root API key correct but account deactivated → None."""
        root_user = _make_user_orm(username=_ROOT_USERNAME, role="root", is_active=False)
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=root_user)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        result = await service.resolve_principal(_ROOT_API_KEY)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_jwt_resolves_to_user_principal(self) -> None:
        """A valid JWT whose subject is a live user resolves to that user's principal."""
        user_id = uuid.uuid4()
        user = _make_user_orm(user_id=user_id, username="bob", role="user")
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        # Mint a real token using the same secret the service was built with
        token = TokenHelpers.mint(subject=str(user_id), secret=_JWT_SECRET, ttl_minutes=_JWT_TTL)
        result = await service.resolve_principal(token)

        assert result is not None
        assert result.user_id == user_id
        assert result.username == "bob"
        assert result.is_root is False

    @pytest.mark.asyncio
    async def test_jwt_with_inactive_user_returns_none(self) -> None:
        """A valid JWT whose subject is an inactive user → None."""
        user_id = uuid.uuid4()
        inactive_user = _make_user_orm(user_id=user_id, is_active=False)
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=inactive_user)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        token = TokenHelpers.mint(subject=str(user_id), secret=_JWT_SECRET, ttl_minutes=_JWT_TTL)
        result = await service.resolve_principal(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_db_api_key_resolves_to_owner(self) -> None:
        """A known DB API key resolves to its owner's principal."""
        owner_id = uuid.uuid4()
        owner = _make_user_orm(user_id=owner_id, username="carol", role="user")
        api_key = _make_api_key_orm(owner_id=owner_id)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=owner)
        user_repo.get_by_username = AsyncMock(return_value=None)

        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=api_key)
        api_key_repo.touch_last_used = AsyncMock()

        service, _, _, _, _ = _make_service(
            user_repo=user_repo, api_key_repo=api_key_repo
        )

        # Use a key that does NOT match the static root key (constant-time compare)
        plaintext = "some-valid-db-key-not-equal-to-root"
        result = await service.resolve_principal(plaintext)

        assert result is not None
        assert result.user_id == owner_id
        assert result.username == "carol"
        api_key_repo.touch_last_used.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_db_api_key_touches_last_used(self) -> None:
        """Resolving a DB API key triggers touch_last_used for telemetry."""
        owner_id = uuid.uuid4()
        owner = _make_user_orm(user_id=owner_id)
        api_key = _make_api_key_orm(owner_id=owner_id)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=owner)
        user_repo.get_by_username = AsyncMock(return_value=None)

        api_key_repo = MagicMock()
        api_key_repo.get_by_hash = AsyncMock(return_value=api_key)
        api_key_repo.touch_last_used = AsyncMock()

        service, _, _, key_repo, _ = _make_service(
            user_repo=user_repo, api_key_repo=api_key_repo
        )

        await service.resolve_principal("some-db-api-key-value")

        # touch_last_used must be called exactly once — the session is the first positional arg
        # (a mock object, not assertable by value), and api_key.id is the second.
        assert key_repo.touch_last_used.await_count == 1
        call_args = key_repo.touch_last_used.call_args
        # Second positional argument must be the api_key id (first is the session mock)
        assert call_args.args[1] == api_key.id


# ── effective_collection_role ───────────────────────────────────────────────────

class TestEffectiveCollectionRole:
    """Tests for AuthService.effective_collection_role()."""

    @pytest.mark.asyncio
    async def test_root_always_gets_admin(self) -> None:
        """A root principal short-circuits to ADMIN on any collection — no DB call."""
        service, _, _, _, grant_repo = _make_service()
        root_principal = Principal(
            user_id=uuid.uuid4(),
            username=_ROOT_USERNAME,
            global_role=UserRole.ROOT,
            is_root=True,
        )
        collection_id = uuid.uuid4()

        role = await service.effective_collection_role(root_principal, collection_id)

        assert role is GrantRole.ADMIN
        # Root short-circuit: no grant lookup should have been made
        grant_repo.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_with_grant_returns_grant_role(self) -> None:
        """A standard user with a grant gets that exact role back."""
        user_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        grant = _make_grant_orm(user_id=user_id, collection_id=collection_id, role="write")

        grant_repo = MagicMock()
        grant_repo.get = AsyncMock(return_value=grant)
        service, _, _, _, _ = _make_service(grant_repo=grant_repo)

        principal = Principal(
            user_id=user_id,
            username="alice",
            global_role=UserRole.USER,
            is_root=False,
        )
        role = await service.effective_collection_role(principal, collection_id)
        assert role is GrantRole.WRITE

    @pytest.mark.asyncio
    async def test_user_without_grant_returns_none(self) -> None:
        """A standard user with no grant on the collection gets None (no access)."""
        user_id = uuid.uuid4()
        grant_repo = MagicMock()
        grant_repo.get = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(grant_repo=grant_repo)

        principal = Principal(
            user_id=user_id,
            username="alice",
            global_role=UserRole.USER,
            is_root=False,
        )
        role = await service.effective_collection_role(principal, uuid.uuid4())
        assert role is None

    @pytest.mark.asyncio
    async def test_all_grant_roles_map_correctly(self) -> None:
        """Each of read/write/admin maps to the corresponding GrantRole enum value."""
        user_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        principal = Principal(
            user_id=user_id,
            username="alice",
            global_role=UserRole.USER,
            is_root=False,
        )

        for role_str, expected in [
            ("read", GrantRole.READ),
            ("write", GrantRole.WRITE),
            ("admin", GrantRole.ADMIN),
        ]:
            grant = _make_grant_orm(
                user_id=user_id, collection_id=collection_id, role=role_str
            )
            grant_repo = MagicMock()
            grant_repo.get = AsyncMock(return_value=grant)
            service, _, _, _, _ = _make_service(grant_repo=grant_repo)

            result = await service.effective_collection_role(principal, collection_id)
            assert result is expected, f"Expected {expected} for role={role_str!r}, got {result}"


# ── authenticate ────────────────────────────────────────────────────────────────

class TestAuthenticate:
    """Tests for AuthService.authenticate() — username/password login path."""

    @pytest.mark.asyncio
    async def test_correct_credentials_return_principal(self) -> None:
        """Valid username + correct password → Principal."""
        password = "correct-password"
        user_id = uuid.uuid4()
        user = _make_user_orm(
            user_id=user_id,
            username="alice",
            role="user",
            password_hash=PasswordHelpers.hash(password),
        )
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=user)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        principal = await service.authenticate("alice", password)

        assert principal is not None
        assert principal.user_id == user_id
        assert principal.username == "alice"
        assert principal.is_root is False

    @pytest.mark.asyncio
    async def test_wrong_password_returns_none(self) -> None:
        """Correct username but wrong password → None."""
        user = _make_user_orm(
            password_hash=PasswordHelpers.hash("correct-password")
        )
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=user)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        result = await service.authenticate(user.username, "wrong-password")
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_username_returns_none(self) -> None:
        """Unknown username → None (user does not exist)."""
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        result = await service.authenticate("ghost", "any-password")
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_user_returns_none(self) -> None:
        """Correct credentials for a deactivated account → None."""
        password = "correct-password"
        inactive_user = _make_user_orm(
            is_active=False,
            password_hash=PasswordHelpers.hash(password),
        )
        user_repo = MagicMock()
        user_repo.get_by_username = AsyncMock(return_value=inactive_user)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        result = await service.authenticate(inactive_user.username, password)
        assert result is None


# ── mint_impersonation_token ──────────────────────────────────────────────────

class TestImpersonationToken:
    """
    Tests for AuthService.mint_impersonation_token() and its resolution round-trip.

    The defining property: an impersonation token authenticates AS the target user (subject =
    target id) while recording the impersonating root in an ``impersonated_by`` claim that surfaces
    on the resolved principal — without granting any extra authority.
    """

    @pytest.mark.asyncio
    async def test_token_resolves_to_target_user_principal(self) -> None:
        """The minted token resolves to the TARGET user's principal (subject = target id)."""
        # 1. Target user the root wants to impersonate
        target_id = uuid.uuid4()
        target = _make_user_orm(user_id=target_id, username="bob", role="user")
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=target)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        # 2. Root mints an impersonation token for the target
        root_id = uuid.uuid4()
        target_principal = Principal.from_user(user_id=target_id, username="bob", role="user")
        token = service.mint_impersonation_token(target=target_principal, impersonator_id=root_id)

        # 3. Resolving that token yields the TARGET principal, not the root
        resolved = await service.resolve_principal(token)
        assert resolved is not None
        assert resolved.user_id == target_id
        assert resolved.username == "bob"
        assert resolved.is_root is False

    @pytest.mark.asyncio
    async def test_resolved_principal_carries_impersonated_by(self) -> None:
        """The resolved principal exposes ``impersonated_by`` = the minting root's id."""
        target_id = uuid.uuid4()
        target = _make_user_orm(user_id=target_id, username="bob", role="user")
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=target)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        root_id = uuid.uuid4()
        target_principal = Principal.from_user(user_id=target_id, username="bob", role="user")
        token = service.mint_impersonation_token(target=target_principal, impersonator_id=root_id)

        resolved = await service.resolve_principal(token)
        assert resolved is not None
        assert resolved.impersonated_by == root_id

    @pytest.mark.asyncio
    async def test_token_embeds_impersonated_by_and_role_claims(self) -> None:
        """The raw token carries the impersonated_by + role audit claims (verified directly)."""
        target_id = uuid.uuid4()
        root_id = uuid.uuid4()
        service, _, _, _, _ = _make_service()
        target_principal = Principal.from_user(user_id=target_id, username="bob", role="user")

        token = service.mint_impersonation_token(target=target_principal, impersonator_id=root_id)

        claims = TokenHelpers.verify(token=token, secret=_JWT_SECRET)
        assert claims is not None
        assert claims["sub"] == str(target_id)
        assert claims["impersonated_by"] == str(root_id)
        assert claims["role"] == "user"

    @pytest.mark.asyncio
    async def test_ordinary_token_has_no_impersonated_by(self) -> None:
        """A normal (non-impersonation) token resolves to a principal with impersonated_by=None."""
        user_id = uuid.uuid4()
        user = _make_user_orm(user_id=user_id, username="carol", role="user")
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        user_repo.get_by_username = AsyncMock(return_value=None)
        service, _, _, _, _ = _make_service(user_repo=user_repo)

        token = TokenHelpers.mint(subject=str(user_id), secret=_JWT_SECRET, ttl_minutes=_JWT_TTL)
        resolved = await service.resolve_principal(token)
        assert resolved is not None
        assert resolved.impersonated_by is None
