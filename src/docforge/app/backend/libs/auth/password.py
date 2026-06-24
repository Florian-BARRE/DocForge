# ====== Code Summary ======
# Argon2 password hashing helpers (static-only). Wraps argon2-cffi's PasswordHasher so the
# rest of the auth layer never touches the algorithm directly. Plaintext passwords are never
# logged or stored — only the resulting hash leaves this module.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from loggerplusplus import loggerplusplus


class PasswordHelpers:
    """
    Static-only helpers for argon2 password hashing and verification.

    A single module-level ``PasswordHasher`` instance carries argon2's default (safe)
    parameters. Hashing and verification are the auth layer's responsibility; repositories
    only ever persist the opaque hash this class produces.
    """

    logger = loggerplusplus.bind(identifier="PasswordHelpers")
    _hasher: PasswordHasher = PasswordHasher()

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PasswordHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def hash(cls, plaintext: str) -> str:
        """
        Hash a plaintext password with argon2.

        Args:
            plaintext (str): The password to hash. Never logged or stored.

        Returns:
            str: The argon2 hash string (safe to persist).
        """
        # 1. Delegate to argon2 (the plaintext is deliberately never logged)
        return cls._hasher.hash(plaintext)

    @classmethod
    def verify(cls, password_hash: str, plaintext: str) -> bool:
        """
        Verify a plaintext password against a stored argon2 hash.

        Args:
            password_hash (str): The stored argon2 hash.
            plaintext (str): The candidate password supplied by the caller.

        Returns:
            bool: True if the password matches, False otherwise (mismatch or malformed hash).
        """
        # 1. argon2 raises on mismatch/invalid hash — translate that into a boolean
        try:
            cls._hasher.verify(password_hash, plaintext)
            return True
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
