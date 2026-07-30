# ====== Code Summary ======
# Startup provisioning of the root credential. When auth is enabled and a root token is configured,
# this idempotently ensures a root AppUser and a full-access ApiKey whose hash matches the token
# exist — so the first request after enabling auth already has a usable key. It is best-effort: a
# store that is unreachable at boot is logged, never fatal (the app still serves its design surface).
# There is NO interactive login in the keys-only model, so the root user's password_hash is a
# sentinel that no credential can ever satisfy.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.services.db.postgresql.tables import ApiKey, AppUser, UserRole

# ====== Local Project Imports ======
from ...context import CONTEXT
from .keys import AuthKeys

# Fixed username of the sole account in the keys-only model.
_ROOT_USERNAME = "root"
# Non-verifiable password sentinel — keys-only means no interactive login is ever attempted.
_NO_LOGIN_SENTINEL = "!"
# Leading chars of the root token shown as its display prefix (also the masked log identifier).
_PREFIX_LENGTH = 12


class AuthBootstrap:
    """Static provisioner for the root user + root API key at application startup."""

    logger = loggerplusplus.bind(identifier="AuthBootstrap")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuthBootstrap is a static-only class and cannot be instantiated.")

    @classmethod
    async def __ensure_root_user(cls) -> AppUser:
        """
        Ensure the root account exists (idempotent by username).

        Returns:
            AppUser: The existing or freshly created root account.
        """
        # 1. Reuse the account if it is already there.
        root = await CONTEXT.database.auth.get_user_by_username(_ROOT_USERNAME)
        if root is not None:
            return root

        # 2. Create it — full ROOT role, active, with a non-verifiable password sentinel.
        root = await CONTEXT.database.auth.create_user(
            AppUser(
                username=_ROOT_USERNAME,
                password_hash=_NO_LOGIN_SENTINEL,
                role=UserRole.ROOT,
                is_active=True,
            )
        )
        cls.logger.info(f"Provisioned root user account")
        return root

    @classmethod
    async def __ensure_root_key(cls, root: AppUser, token: str) -> None:
        """
        Ensure the root API key exists for the configured token (idempotent by hash).

        Args:
            root (AppUser): The owning root account.
            token (str): The bootstrap root token plaintext (never logged in full).
        """
        # 1. Skip if a key with this exact hash is already present.
        key_hash = AuthKeys.hash_key(token)
        if await CONTEXT.database.auth.get_key_by_hash(key_hash) is not None:
            cls.logger.info(f"Root API key already present - bootstrap is a no-op")
            return

        # 2. Persist a full-access (NULL permissions) key owned by root; store hash + prefix only.
        prefix = token[:_PREFIX_LENGTH]
        await CONTEXT.database.auth.create_key(
            ApiKey(
                user_id=root.id,
                name=_ROOT_USERNAME,
                key_hash=key_hash,
                prefix=prefix,
                permissions=None,
            )
        )
        cls.logger.info(f"Provisioned root API key (prefix={prefix}...)")

    @classmethod
    async def ensure_root_credential(cls) -> None:
        """
        Provision the root user + key when auth is on and a token is configured.

        Best-effort: any store error at boot is logged and swallowed so the app still starts.
        """
        # 1. Nothing to do unless auth is on AND a bootstrap token was supplied.
        if not RUNTIME_CONFIG.AUTH_ENABLED or not RUNTIME_CONFIG.AUTH_ROOT_TOKEN:
            return

        # 2. Provision idempotently; a store down at boot must not crash the app.
        try:
            root = await cls.__ensure_root_user()
            await cls.__ensure_root_key(root, RUNTIME_CONFIG.AUTH_ROOT_TOKEN)
        except Exception as exc:
            cls.logger.error(
                f"Root credential bootstrap skipped (store unreachable at boot): {exc}"
            )


__all__ = ["AuthBootstrap"]
