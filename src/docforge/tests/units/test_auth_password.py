# ====== Code Summary ======
# Unit tests for PasswordHelpers — argon2 hash/verify round-trip and failure modes.
# No mocks needed: PasswordHelpers is a pure static class with no external dependencies.

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.libs.auth.password import PasswordHelpers


class TestPasswordHash:
    """Tests for PasswordHelpers.hash()."""

    def test_hash_returns_string(self) -> None:
        """hash() returns a non-empty string."""
        result = PasswordHelpers.hash("my-password")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_produces_argon2_format(self) -> None:
        """The returned hash starts with the argon2 identifier prefix."""
        result = PasswordHelpers.hash("my-password")
        # argon2-cffi produces the $argon2id$ or $argon2i$ prefixed PHC string.
        assert result.startswith("$argon2")

    def test_hash_is_non_deterministic(self) -> None:
        """Two hashes of the same password are different (salted)."""
        h1 = PasswordHelpers.hash("same-password")
        h2 = PasswordHelpers.hash("same-password")
        assert h1 != h2

    def test_hash_is_not_class_instantiable(self) -> None:
        """PasswordHelpers blocks direct instantiation."""
        with pytest.raises(TypeError):
            PasswordHelpers()  # type: ignore[call-arg]


class TestPasswordVerify:
    """Tests for PasswordHelpers.verify()."""

    def test_verify_correct_password_returns_true(self) -> None:
        """A plaintext that was used to produce the hash verifies successfully."""
        plaintext = "correct-horse-battery-staple"
        stored_hash = PasswordHelpers.hash(plaintext)
        assert PasswordHelpers.verify(stored_hash, plaintext) is True

    def test_verify_wrong_password_returns_false(self) -> None:
        """A different plaintext never verifies against a hash."""
        stored_hash = PasswordHelpers.hash("correct-password")
        assert PasswordHelpers.verify(stored_hash, "wrong-password") is False

    def test_verify_empty_password_returns_false(self) -> None:
        """An empty candidate string does not verify."""
        stored_hash = PasswordHelpers.hash("non-empty-password")
        assert PasswordHelpers.verify(stored_hash, "") is False

    def test_verify_garbage_hash_returns_false(self) -> None:
        """A malformed hash string never raises — it just returns False."""
        assert PasswordHelpers.verify("not-a-hash-at-all", "any-password") is False

    def test_verify_tampered_hash_returns_false(self) -> None:
        """A single-character corruption in the hash causes verification to fail."""
        stored_hash = PasswordHelpers.hash("original")
        # Corrupt the last character
        tampered = stored_hash[:-1] + ("X" if stored_hash[-1] != "X" else "Y")
        assert PasswordHelpers.verify(tampered, "original") is False
