# ====== Code Summary ======
# Unit tests for RUNTIME_CONFIG.validate() — the auth-secret guard added to the app config.
#
# Strategy: RUNTIME_CONFIG is a class whose attributes are set at import time from the
# environment. Tests monkeypatch the class-level attributes directly (not the environment)
# so each case is isolated from the actual .env that was loaded by the test process.
# validate() only reads class attributes, so this is fully faithful.

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from config.runtime_config import (
    RUNTIME_CONFIG,
    _PLACEHOLDER_JWT_SECRET,
    _PLACEHOLDER_ROOT_API_KEY,
    _PLACEHOLDER_ROOT_PASSWORD,
    _MIN_JWT_SECRET_LEN,
)

# A strong, non-placeholder set of auth secrets used in the "passes" cases.
_GOOD_API_KEY = "a-real-root-api-key-that-is-not-the-placeholder"
_GOOD_JWT_SECRET = "a-real-jwt-secret-that-is-definitely-32-chars-long"
_GOOD_PASSWORD = "a-real-root-password-not-the-placeholder"


def _configure_auth_on(monkeypatch: pytest.MonkeyPatch, **overrides: str | bool | int) -> None:
    """
    Helper: set AUTH_ENABLED=True + the three auth secrets on RUNTIME_CONFIG via monkeypatch.

    Callers may override any field by name to inject an unsafe value for a specific test.
    """
    defaults: dict[str, str | bool | int] = {
        "AUTH_ENABLED": True,
        "AUTH_ROOT_API_KEY": _GOOD_API_KEY,
        "AUTH_JWT_SECRET": _GOOD_JWT_SECRET,
        "AUTH_ROOT_PASSWORD": _GOOD_PASSWORD,
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(RUNTIME_CONFIG, name, value, raising=False)


class TestValidateAuthOff:
    """When AUTH_ENABLED is false, validate() must never raise regardless of secret values."""

    def test_inert_with_placeholder_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Placeholder defaults are acceptable when auth is off — validate() is a no-op."""
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False, raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_API_KEY", _PLACEHOLDER_ROOT_API_KEY, raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_JWT_SECRET", _PLACEHOLDER_JWT_SECRET, raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_PASSWORD", _PLACEHOLDER_ROOT_PASSWORD, raising=False)
        # Must not raise
        RUNTIME_CONFIG.validate()

    def test_inert_with_empty_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty secrets are acceptable when auth is off."""
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False, raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_API_KEY", "", raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_JWT_SECRET", "", raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ROOT_PASSWORD", "", raising=False)
        RUNTIME_CONFIG.validate()

    def test_inert_with_short_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A JWT secret shorter than 32 chars is acceptable when auth is off."""
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False, raising=False)
        monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_JWT_SECRET", "short", raising=False)
        RUNTIME_CONFIG.validate()


class TestValidateAuthOnPasses:
    """When AUTH_ENABLED is true and all secrets are real, validate() passes silently."""

    def test_passes_with_strong_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All secrets set to non-placeholder values of adequate length → no exception."""
        _configure_auth_on(monkeypatch)
        RUNTIME_CONFIG.validate()

    def test_passes_with_jwt_secret_exactly_min_length(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A JWT secret of exactly _MIN_JWT_SECRET_LEN characters is accepted."""
        _configure_auth_on(
            monkeypatch,
            AUTH_JWT_SECRET="x" * _MIN_JWT_SECRET_LEN,
        )
        RUNTIME_CONFIG.validate()

    def test_passes_with_jwt_secret_longer_than_min(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A JWT secret much longer than 32 chars is always accepted."""
        _configure_auth_on(
            monkeypatch,
            AUTH_JWT_SECRET="x" * (_MIN_JWT_SECRET_LEN * 2),
        )
        RUNTIME_CONFIG.validate()


class TestValidateAuthOnRaisesOnPlaceholders:
    """When AUTH_ENABLED is true, placeholder defaults must be rejected."""

    def test_raises_on_placeholder_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTH_ROOT_API_KEY still at its placeholder → RuntimeError."""
        _configure_auth_on(monkeypatch, AUTH_ROOT_API_KEY=_PLACEHOLDER_ROOT_API_KEY)
        with pytest.raises(RuntimeError, match="AUTH_ROOT_API_KEY"):
            RUNTIME_CONFIG.validate()

    def test_raises_on_placeholder_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTH_JWT_SECRET still at its placeholder → RuntimeError."""
        _configure_auth_on(monkeypatch, AUTH_JWT_SECRET=_PLACEHOLDER_JWT_SECRET)
        with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
            RUNTIME_CONFIG.validate()

    def test_raises_on_placeholder_root_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTH_ROOT_PASSWORD still at its placeholder → RuntimeError."""
        _configure_auth_on(monkeypatch, AUTH_ROOT_PASSWORD=_PLACEHOLDER_ROOT_PASSWORD)
        with pytest.raises(RuntimeError, match="AUTH_ROOT_PASSWORD"):
            RUNTIME_CONFIG.validate()

    def test_raises_on_empty_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty AUTH_ROOT_API_KEY is rejected just like a placeholder."""
        _configure_auth_on(monkeypatch, AUTH_ROOT_API_KEY="")
        with pytest.raises(RuntimeError, match="AUTH_ROOT_API_KEY"):
            RUNTIME_CONFIG.validate()

    def test_raises_on_empty_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty AUTH_JWT_SECRET is rejected."""
        _configure_auth_on(monkeypatch, AUTH_JWT_SECRET="")
        with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
            RUNTIME_CONFIG.validate()

    def test_raises_on_empty_root_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty AUTH_ROOT_PASSWORD is rejected."""
        _configure_auth_on(monkeypatch, AUTH_ROOT_PASSWORD="")
        with pytest.raises(RuntimeError, match="AUTH_ROOT_PASSWORD"):
            RUNTIME_CONFIG.validate()

    def test_error_message_names_all_offending_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When multiple secrets are bad, all names appear in the error message."""
        _configure_auth_on(
            monkeypatch,
            AUTH_ROOT_API_KEY=_PLACEHOLDER_ROOT_API_KEY,
            AUTH_JWT_SECRET=_PLACEHOLDER_JWT_SECRET,
            AUTH_ROOT_PASSWORD=_PLACEHOLDER_ROOT_PASSWORD,
        )
        with pytest.raises(RuntimeError) as exc_info:
            RUNTIME_CONFIG.validate()
        msg = str(exc_info.value)
        assert "AUTH_ROOT_API_KEY" in msg
        assert "AUTH_JWT_SECRET" in msg
        assert "AUTH_ROOT_PASSWORD" in msg


class TestValidateAuthOnRaisesOnShortJwtSecret:
    """A non-placeholder but too-short JWT secret must also be rejected."""

    def test_raises_on_short_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A JWT secret shorter than _MIN_JWT_SECRET_LEN chars → RuntimeError."""
        short_secret = "x" * (_MIN_JWT_SECRET_LEN - 1)
        _configure_auth_on(monkeypatch, AUTH_JWT_SECRET=short_secret)
        with pytest.raises(RuntimeError, match="too short"):
            RUNTIME_CONFIG.validate()

    def test_raises_on_one_char_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even a non-placeholder single-character JWT secret is rejected."""
        _configure_auth_on(monkeypatch, AUTH_JWT_SECRET="x")
        with pytest.raises(RuntimeError, match="too short"):
            RUNTIME_CONFIG.validate()

    def test_error_message_references_min_length(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The error message states the minimum length requirement."""
        _configure_auth_on(monkeypatch, AUTH_JWT_SECRET="tooshort")
        with pytest.raises(RuntimeError) as exc_info:
            RUNTIME_CONFIG.validate()
        assert str(_MIN_JWT_SECRET_LEN) in str(exc_info.value)
