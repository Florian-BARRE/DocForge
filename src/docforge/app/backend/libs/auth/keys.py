# ====== Code Summary ======
# API-key generation and hashing. Keys are HIGH-ENTROPY secrets, so they are hashed with a plain
# deterministic SHA-256 (NOT argon2): the authentication hot path looks a key up BY its hash, which
# a salted KDF makes impossible. The plaintext is shown to the caller exactly once (on create) and
# is never stored — only its hash and a short display prefix are persisted.

# ====== Standard Library Imports ======
import hashlib
import secrets

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class AuthKeys:
    """Static helpers for API-key generation and deterministic hashing."""

    logger = loggerplusplus.bind(identifier="AuthKeys")

    # Human-readable plaintext prefix — marks a token as a DocForge key at a glance.
    _PLAINTEXT_PREFIX = "df_"
    # Number of leading plaintext chars stored/shown as the key's display prefix.
    _DISPLAY_PREFIX_LENGTH = 12
    # Entropy (bytes) of the random component; token_urlsafe expands this to ~43 chars.
    _TOKEN_ENTROPY_BYTES = 32

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuthKeys is a static-only class and cannot be instantiated.")

    @staticmethod
    def hash_key(plaintext: str) -> str:
        """
        Hash an API key deterministically for by-hash lookup.

        Args:
            plaintext (str): The raw API key.

        Returns:
            str: The hex-encoded SHA-256 digest stored in the ``api_key.key_hash`` column.
        """
        # 1. Deterministic digest — the same plaintext always yields the same hash (the lookup key).
        return hashlib.sha256(plaintext.encode()).hexdigest()

    @classmethod
    def generate_key(cls) -> tuple[str, str, str]:
        """
        Generate a fresh API key.

        Returns:
            tuple[str, str, str]: The ``(plaintext, prefix, key_hash)`` triple. Only the prefix and
            the hash are ever persisted; the plaintext is returned to the caller exactly once.
        """
        # 1. Build the plaintext: a recognizable prefix + a high-entropy URL-safe random tail.
        plaintext = f"{cls._PLAINTEXT_PREFIX}{secrets.token_urlsafe(cls._TOKEN_ENTROPY_BYTES)}"

        # 2. Derive the stored display prefix and the by-hash lookup digest.
        prefix = plaintext[: cls._DISPLAY_PREFIX_LENGTH]
        key_hash = cls.hash_key(plaintext)

        # 3. Hand back all three; the caller persists prefix + hash and shows plaintext once.
        return plaintext, prefix, key_hash


__all__ = ["AuthKeys"]
