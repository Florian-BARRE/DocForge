# ====== Code Summary ======
# Unit tests for TokenHelpers — JWT mint/verify round-trip and rejection cases.
# TokenHelpers has no state or external I/O; all tests are synchronous.

# ====== Standard Library Imports ======
import time
import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.libs.auth.tokens import TokenHelpers

_SECRET = "test-signing-secret-never-used-in-prod"
_TTL = 60  # 60-minute TTL — well beyond any test run


class TestTokenMint:
    """Tests for TokenHelpers.mint()."""

    def test_mint_returns_non_empty_string(self) -> None:
        """mint() produces a non-empty string."""
        token = TokenHelpers.mint(
            subject=str(uuid.uuid4()), secret=_SECRET, ttl_minutes=_TTL
        )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_mint_produces_three_part_jwt(self) -> None:
        """A minted token has exactly three dot-separated segments (header.payload.signature).

        Note: we do NOT assert non-determinism here because Python's datetime.now() has
        only second-level precision on some platforms (notably Windows).  Two tokens
        minted within the same second therefore encode identical iat/exp values and
        produce the same deterministic HMAC — they ARE the same token.  That is correct
        behaviour for a one-second window; testing randomness over a wall-clock sleep
        would make this test flaky.
        """
        subject = str(uuid.uuid4())
        token = TokenHelpers.mint(subject=subject, secret=_SECRET, ttl_minutes=_TTL)
        # A well-formed JWT always has exactly two dots separating header, payload, signature.
        assert token.count(".") == 2

    def test_is_not_class_instantiable(self) -> None:
        """TokenHelpers blocks direct instantiation."""
        with pytest.raises(TypeError):
            TokenHelpers()  # type: ignore[call-arg]

    def test_extra_claims_are_embedded(self) -> None:
        """extra_claims are merged into the token payload and survive a verify round-trip."""
        scope_value = str(uuid.uuid4())
        token = TokenHelpers.mint(
            subject=str(uuid.uuid4()),
            secret=_SECRET,
            ttl_minutes=_TTL,
            extra_claims={"scope": scope_value, "role": "root"},
        )
        claims = TokenHelpers.verify(token=token, secret=_SECRET)
        assert claims is not None
        assert claims["scope"] == scope_value
        assert claims["role"] == "root"

    def test_extra_claims_cannot_override_reserved_claims(self) -> None:
        """A caller-supplied 'sub' in extra_claims must NOT re-target the token."""
        real_subject = str(uuid.uuid4())
        token = TokenHelpers.mint(
            subject=real_subject,
            secret=_SECRET,
            ttl_minutes=_TTL,
            extra_claims={"sub": "attacker-controlled-subject"},
        )
        claims = TokenHelpers.verify(token=token, secret=_SECRET)
        assert claims is not None
        # The genuine subject wins — the injected one is ignored.
        assert claims["sub"] == real_subject


class TestTokenVerify:
    """Tests for TokenHelpers.verify()."""

    def test_verify_valid_token_returns_claims(self) -> None:
        """A freshly minted token verifies and returns a claims dict with sub."""
        subject = str(uuid.uuid4())
        token = TokenHelpers.mint(subject=subject, secret=_SECRET, ttl_minutes=_TTL)
        claims = TokenHelpers.verify(token=token, secret=_SECRET)
        assert claims is not None
        assert claims["sub"] == subject

    def test_verify_claims_contain_iat_and_exp(self) -> None:
        """Verified claims include iat (issued-at) and exp (expiry) fields."""
        token = TokenHelpers.mint(
            subject=str(uuid.uuid4()), secret=_SECRET, ttl_minutes=_TTL
        )
        claims = TokenHelpers.verify(token=token, secret=_SECRET)
        assert claims is not None
        assert "iat" in claims
        assert "exp" in claims

    def test_verify_wrong_secret_returns_none(self) -> None:
        """A token signed with a different secret fails verification."""
        token = TokenHelpers.mint(
            subject=str(uuid.uuid4()), secret=_SECRET, ttl_minutes=_TTL
        )
        result = TokenHelpers.verify(token=token, secret="wrong-secret")
        assert result is None

    def test_verify_tampered_payload_returns_none(self) -> None:
        """Corrupting the token payload causes signature verification to fail."""
        token = TokenHelpers.mint(
            subject=str(uuid.uuid4()), secret=_SECRET, ttl_minutes=_TTL
        )
        # Corrupt the middle segment (payload) by appending garbage
        parts = token.split(".")
        tampered = ".".join([parts[0], parts[1] + "ZZZ", parts[2]])
        result = TokenHelpers.verify(token=tampered, secret=_SECRET)
        assert result is None

    def test_verify_garbage_token_returns_none(self) -> None:
        """A completely invalid string never raises — it returns None."""
        result = TokenHelpers.verify(token="not.a.jwt", secret=_SECRET)
        assert result is None

    def test_verify_empty_token_returns_none(self) -> None:
        """An empty string is not a valid token."""
        result = TokenHelpers.verify(token="", secret=_SECRET)
        assert result is None

    def test_verify_expired_token_returns_none(self) -> None:
        """A token with TTL=0 minutes is expired immediately after minting."""
        # TTL=0 means exp == iat, so the token is already expired
        token = TokenHelpers.mint(
            subject=str(uuid.uuid4()), secret=_SECRET, ttl_minutes=0
        )
        # Allow a brief moment to pass so exp is definitely in the past
        time.sleep(0.1)
        result = TokenHelpers.verify(token=token, secret=_SECRET)
        # Expired tokens should return None (PyJWT enforces exp)
        assert result is None
