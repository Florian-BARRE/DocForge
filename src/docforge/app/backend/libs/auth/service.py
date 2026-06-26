# ====== Code Summary ======
# AuthService — the heart of the auth layer. Owns credential resolution (root static key | password
# JWT | DB API key), username/password authentication, and root bootstrap. In the keys-only model
# the SOLE delegated-access mechanism is the API key: its per-collection capability scope rides on
# the resolved Principal. Pure-ish service: it opens its own DB sessions via the injected
# PostgresClient and delegates persistence to the user + api-key repositories. Never logs secrets.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.models import UserRole
from common_libs.storage.postgres.repositories import (
    ApiKeyRepository,
    UserRepository,
)

# ====== Local Project Imports ======
from .models import Principal
from .password import PasswordHelpers
from .tokens import TokenHelpers

# Length (chars) of the human-visible API-key prefix stored for UI identification.
_KEY_PREFIX_LEN = 8
# Number of random bytes in a generated API key (token_urlsafe yields ~1.3 chars/byte).
_KEY_RANDOM_BYTES = 32


class AuthService(LoggerClass):
    """
    Authentication + authorization service.

    Resolves request credentials into a ``Principal``, authenticates username/password logins, and
    bootstraps the single root account at startup. It opens short-lived sessions through the injected
    ``PostgresClient`` so callers (routes, dependencies) never have to thread a session into auth
    calls. Per-collection authorization is no longer a DB lookup: it is the capability scope carried
    on the Principal (None = full access; a dict = a scoped API key).
    """

    def __init__(
        self,
        *,
        postgres: PostgresClient,
        user_repo: UserRepository,
        api_key_repo: ApiKeyRepository,
        root_api_key: str,
        jwt_secret: str,
        jwt_ttl_minutes: int,
        root_username: str,
        root_password: str,
    ) -> None:
        """
        Wire the auth service with its storage collaborators and secrets.

        Args:
            postgres (PostgresClient): Session factory for all auth DB access.
            user_repo (UserRepository): Users data access.
            api_key_repo (ApiKeyRepository): API keys data access.
            root_api_key (str): Static break-glass root Bearer key (constant-time compared).
            jwt_secret (str): HS256 signing secret for minted access tokens.
            jwt_ttl_minutes (int): Lifetime of minted access tokens in minutes.
            root_username (str): Root account login handle (bootstrap).
            root_password (str): Root account plaintext password (hashed at bootstrap; never stored).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._user_repo = user_repo
        self._api_key_repo = api_key_repo
        self._root_api_key = root_api_key
        self._jwt_secret = jwt_secret
        self._jwt_ttl_minutes = jwt_ttl_minutes
        self._root_username = root_username
        self._root_password = root_password
        # Cached id of the bootstrapped root account. Populated by bootstrap_root() at startup so the
        # static-root-key path can build a Principal WITHOUT a per-request DB lookup. None until then.
        self._root_user_id: uuid.UUID | None = None

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _hash_api_key(plaintext_key: str) -> str:
        """
        Hash an API key for storage / lookup (sha256 hex).

        API keys are high-entropy random tokens, so a fast unsalted sha256 is appropriate (unlike
        passwords, which use argon2). The same hash is used at creation and on every lookup.

        Args:
            plaintext_key (str): The raw API key.

        Returns:
            str: Hex sha256 digest.
        """
        return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()

    async def _principal_from_user_id(
        self, user_id: uuid.UUID, *, permissions: dict | None = None
    ) -> Principal | None:
        """
        Load an active user by id and build its Principal (None if missing/inactive).

        Args:
            user_id (uuid.UUID): The user id to resolve.
            permissions (dict | None): The API-key permission scope to attach (None = full access).

        Returns:
            Principal | None: The principal, or None when the user is unknown or deactivated.
        """
        # 1. Fetch the user and reject unknown / soft-disabled accounts
        async with self._postgres.session() as session:
            user = await self._user_repo.get_by_id(session, user_id)
        if user is None or not user.is_active:
            return None

        # 2. Project the ORM row into the immutable principal, carrying the key's scope
        return Principal.from_user(
            user_id=user.id, username=user.username, role=user.role, permissions=permissions
        )

    async def _resolve_jwt(self, bearer: str) -> Principal | None:
        """
        Resolve a Bearer value as a password-login JWT (step 2 of credential resolution).

        A JWT is only ever minted by ``/auth/login`` for the root account, so it always resolves to
        a full-access (unscoped) principal.

        Args:
            bearer (str): The raw Bearer token value.

        Returns:
            Principal | None: The principal if the JWT is valid and its subject is a live user.
        """
        # 1. Verify signature + expiry
        claims = TokenHelpers.verify(token=bearer, secret=self._jwt_secret)
        if claims is None:
            return None

        # 2. The subject must be a parseable user id
        subject = claims.get("sub")
        if not subject:
            return None
        try:
            user_id = uuid.UUID(str(subject))
        except (ValueError, TypeError):
            return None

        # 3. Resolve the user behind the subject (full access — a login JWT carries no key scope)
        return await self._principal_from_user_id(user_id)

    async def _resolve_api_key(self, bearer: str) -> Principal | None:
        """
        Resolve a Bearer value as a DB API key (step 3 of credential resolution).

        The key's stored ``permissions`` scope is attached to the resolved principal so the
        capability dependencies can authorize per collection. A NULL scope (legacy key) yields a
        full-access principal for backward compatibility.

        Args:
            bearer (str): The raw API key value.

        Returns:
            Principal | None: The owning principal (scoped by the key) if the key exists/active.
        """
        # 1. Hash then look up a non-revoked key
        key_hash = self._hash_api_key(bearer)
        async with self._postgres.session() as session:
            api_key = await self._api_key_repo.get_by_hash(session, key_hash)
            if api_key is None:
                return None
            # 2. Best-effort last-used telemetry on the hot auth path (same session/txn)
            await self._api_key_repo.touch_last_used(session, api_key.id)
            owner_id = api_key.user_id
            permissions = api_key.permissions

        # 3. Resolve the key's owner, carrying the key's capability scope (None = full access)
        return await self._principal_from_user_id(owner_id, permissions=permissions)

    # ── Public ────────────────────────────────────────────────────────────────

    def generate_api_key(self) -> tuple[str, str, str]:
        """
        Generate a fresh API key and its derived storage fields.

        The plaintext is returned to the caller exactly once (shown to the user, never stored);
        only the hash + prefix are persisted.

        Returns:
            tuple[str, str, str]: ``(plaintext_key, key_hash, prefix)``.
        """
        # 1. Random URL-safe token, then derive its hash + display prefix
        plaintext_key = secrets.token_urlsafe(_KEY_RANDOM_BYTES)
        key_hash = self._hash_api_key(plaintext_key)
        prefix = plaintext_key[:_KEY_PREFIX_LEN]
        return plaintext_key, key_hash, prefix

    def mint_token(self, principal: Principal) -> str:
        """
        Mint a JWT access token for an authenticated principal.

        Args:
            principal (Principal): The authenticated user.

        Returns:
            str: The signed JWT access token.
        """
        return TokenHelpers.mint(
            subject=str(principal.user_id),
            secret=self._jwt_secret,
            ttl_minutes=self._jwt_ttl_minutes,
        )

    async def authenticate(self, username: str, password: str) -> Principal | None:
        """
        Authenticate a username/password pair (the login path).

        Args:
            username (str): Login handle.
            password (str): Plaintext password (verified against the stored hash, never logged).

        Returns:
            Principal | None: The principal on success, None on unknown user / bad password /
            deactivated account.
        """
        # 1. Look up the user (reject unknown handles)
        async with self._postgres.session() as session:
            user = await self._user_repo.get_by_username(session, username)
        if user is None:
            self.logger.warning(f"Login failed (unknown username): username={username!r}")
            return None

        # 2. Reject deactivated accounts before spending a hash verification
        if not user.is_active:
            self.logger.warning(f"Login failed (inactive account): username={username!r}")
            return None

        # 3. Verify the password against the stored argon2 hash
        if not PasswordHelpers.verify(user.password_hash, password):
            self.logger.warning(f"Login failed (bad password): username={username!r}")
            return None

        self.logger.info(f"Login ok: username={username!r} user_id={user.id}")
        return Principal.from_user(user_id=user.id, username=user.username, role=user.role)

    async def resolve_principal(self, bearer: str | None) -> Principal | None:
        """
        Resolve a raw Bearer credential into a Principal, in priority order.

        Resolution order:
            1. Static root API key (constant-time compare) → the bootstrapped root user (full access).
            2. Valid password JWT → the user named by its subject (full access).
            3. DB API key (hash lookup, non-revoked) → the key's owner, scoped by the key's
               ``permissions`` (NULL scope = full access, back-compat).
        The first match wins; if none match, the credential is invalid.

        Args:
            bearer (str | None): The raw Bearer value (already stripped of the "Bearer " prefix).

        Returns:
            Principal | None: The resolved principal, or None when the credential is invalid.
        """
        # 0. No credential supplied — nothing to resolve
        if not bearer:
            return None

        # 1. Static root key — constant-time compare guards against timing attacks. A match resolves
        #    to the bootstrapped root account (break-glass / tests / MCP) with FULL access. The root
        #    id is cached at bootstrap, so the hot path builds the Principal from config WITHOUT a DB
        #    round-trip. The cache is only empty if bootstrap_root() never ran — then fail closed.
        if hmac.compare_digest(bearer, self._root_api_key):
            if self._root_user_id is not None:
                return Principal.from_user(
                    user_id=self._root_user_id,
                    username=self._root_username,
                    role=UserRole.ROOT.value,
                )
            # Root key configured but bootstrap never populated the cache — fail closed.
            self.logger.warning(
                f"Root API key accepted but root account is not bootstrapped — denying."
            )
            return None

        # 2. Password JWT (full access)
        jwt_principal = await self._resolve_jwt(bearer)
        if jwt_principal is not None:
            return jwt_principal

        # 3. DB API key (scoped by its permissions)
        return await self._resolve_api_key(bearer)

    async def bootstrap_root(self) -> None:
        """
        Idempotently ensure the configured root account exists (startup step).

        Hashes the configured root password and upserts the root user. Safe to call on every
        boot: it refreshes the hash and re-asserts the root role + active flag.
        """
        # 1. Hash the configured plaintext password (the plaintext is never persisted/logged)
        password_hash = PasswordHelpers.hash(self._root_password)

        # 2. Upsert the single root account
        async with self._postgres.session() as session:
            root = await self._user_repo.upsert_root(
                session, username=self._root_username, password_hash=password_hash
            )

        # 3. Cache the root id so the static-root-key auth path needs no per-request DB lookup
        self._root_user_id = root.id
        self.logger.info(f"Root account ready: username={root.username!r} user_id={root.id}")
