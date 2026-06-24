# ====== Code Summary ======
# App (FastAPI) runtime config — extends the shared BaseRuntimeConfig with web-only
# settings the worker never needs (FastAPI, CORS, SSE fan-out, resource admission).
# Imported as `from config import RUNTIME_CONFIG` (resolves to this app's config tree).

# ====== Third-Party Library Imports ======
from configplusplus import env

# ====== Internal Project Imports ======
from base_config import BaseRuntimeConfig

# Insecure placeholder defaults for the auth secrets. They keep the API runnable out-of-the-box
# while AUTH_ENABLED is false, but validate() rejects them the moment auth is turned ON — the guard
# references THESE constants (not duplicated literals) so the default and the check never drift.
_PLACEHOLDER_ROOT_PASSWORD = "change_me_root_password"
_PLACEHOLDER_ROOT_API_KEY = "change_me_root_api_key"
_PLACEHOLDER_JWT_SECRET = "change_me_jwt_secret"
# Minimum acceptable JWT signing-secret length when auth is on — HS256 needs real entropy
# (pyjwt itself warns on weak secrets).
_MIN_JWT_SECRET_LEN = 32


class RUNTIME_CONFIG(BaseRuntimeConfig):
    """
    FastAPI app runtime configuration.

    Inherits every shared variable from BaseRuntimeConfig (logging, storage, providers…)
    and adds the web-facing settings used only by the API process.
    """

    # ───── FastAPI ─────
    FASTAPI_APP_NAME: str = env("FASTAPI_APP_NAME", default="DocForge")
    FASTAPI_DEBUG_MODE: bool = env("FASTAPI_DEBUG_MODE", cast=bool, default="false")
    CORS_ALLOWED_ORIGINS: str = env("CORS_ALLOWED_ORIGINS", default="http://localhost:5173")
    # Application version surfaced in OpenAPI docs and the /health/ping endpoint.
    APP_VERSION: str = env("APP_VERSION", default="0.1.0")

    # ───── Real-time streaming (brick C) ─────
    # SSE comment-ping cadence (s) — keeps proxies/LBs from killing idle streams.
    SSE_KEEPALIVE_SECONDS: int = env("SSE_KEEPALIVE_SECONDS", cast=int, default="15")
    # Per-client SSE fan-out queue size; on overflow the broadcaster drops the oldest
    # event so one slow browser cannot grow memory unboundedly (back-pressure).
    SSE_CLIENT_QUEUE_MAXSIZE: int = env("SSE_CLIENT_QUEUE_MAXSIZE", cast=int, default="100")

    # ───── Resource admission / back-pressure (brick D) ─────
    # The enqueue gate lives in the API process (backend/libs/admission), never the worker.
    ADMISSION_ENABLED: bool = env("ADMISSION_ENABLED", cast=bool, default="true")
    ADMISSION_MAX_QUEUE_DEPTH: int = env("ADMISSION_MAX_QUEUE_DEPTH", cast=int, default="0")
    ADMISSION_MAX_IN_FLIGHT_GLOBAL: int = env("ADMISSION_MAX_IN_FLIGHT_GLOBAL", cast=int, default="0")

    # ───── Authentication / authorization ─────
    # Auth is a web-only concern (the worker never serves requests), so these live here
    # rather than in the shared BaseRuntimeConfig. Secrets are auto-masked by configplusplus
    # because their names contain PASSWORD / API_KEY / SECRET / TOKEN.
    # Kill-switch: when false, every protected route receives a synthetic root principal so
    # the API behaves exactly as it did before auth (rétro-compat / unauthenticated tests).
    AUTH_ENABLED: bool = env("AUTH_ENABLED", cast=bool, default="false")
    # Break-glass root account, bootstrapped at startup (upsert_root). The password is hashed
    # at boot; the static API key is compared in constant time on every request.
    AUTH_ROOT_USERNAME: str = env("AUTH_ROOT_USERNAME", default="root")
    AUTH_ROOT_PASSWORD: str = env("AUTH_ROOT_PASSWORD", default=_PLACEHOLDER_ROOT_PASSWORD)
    AUTH_ROOT_API_KEY: str = env("AUTH_ROOT_API_KEY", default=_PLACEHOLDER_ROOT_API_KEY)
    # HS256 signing secret for minted JWT access tokens, and their lifetime in minutes.
    AUTH_JWT_SECRET: str = env("AUTH_JWT_SECRET", default=_PLACEHOLDER_JWT_SECRET)
    AUTH_JWT_TTL_MINUTES: int = env("AUTH_JWT_TTL_MINUTES", cast=int, default="720")

    @classmethod
    def validate(cls) -> None:
        """
        Validate the runtime configuration, failing fast on unsafe auth settings.

        Runs the base validation first, then — ONLY when ``AUTH_ENABLED`` is true — refuses to start
        if any auth secret is still its insecure placeholder default, empty, or (for the JWT secret)
        too short for HS256. The error names every offending variable so the operator knows exactly
        what to fix. When auth is off these checks are skipped entirely (the placeholders are fine).

        Raises:
            RuntimeError: When auth is enabled but one or more secrets are unsafe.
        """
        # 1. Always run the inherited base validation first
        super().validate()

        # 2. The guard only bites when auth is actually enabled
        if not cls.AUTH_ENABLED:
            return

        # 3. Collect every unsafe secret (empty or still the placeholder default)
        problems: list[str] = []
        insecure = {
            "AUTH_ROOT_API_KEY": (cls.AUTH_ROOT_API_KEY, _PLACEHOLDER_ROOT_API_KEY),
            "AUTH_JWT_SECRET": (cls.AUTH_JWT_SECRET, _PLACEHOLDER_JWT_SECRET),
            "AUTH_ROOT_PASSWORD": (cls.AUTH_ROOT_PASSWORD, _PLACEHOLDER_ROOT_PASSWORD),
        }
        for name, (value, placeholder) in insecure.items():
            if not value or value == placeholder:
                problems.append(f"{name} is unset or still the insecure default")

        # 4. The JWT secret additionally needs real entropy for HS256
        if cls.AUTH_JWT_SECRET and len(cls.AUTH_JWT_SECRET) < _MIN_JWT_SECRET_LEN:
            problems.append(
                f"AUTH_JWT_SECRET is too short (< {_MIN_JWT_SECRET_LEN} chars) for HS256"
            )

        # 5. Fail fast with a message that names every offending variable
        if problems:
            raise RuntimeError(
                "AUTH_ENABLED is true but the auth configuration is unsafe: "
                + "; ".join(problems)
                + ". Set strong values for these variables before enabling authentication."
            )


__all__ = ["RUNTIME_CONFIG"]
