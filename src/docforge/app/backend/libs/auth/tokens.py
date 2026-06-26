# ====== Code Summary ======
# JWT minting and verification helpers (static-only). HS256 access tokens carry the user id as
# the subject claim. Minting and verification are pure functions of the secret + TTL passed in by
# the caller (AuthService), so this module reads no config and holds no state.

# ====== Standard Library Imports ======
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# ====== Third-Party Library Imports ======
import jwt
from loggerplusplus import loggerplusplus

# Signing algorithm for all DocForge access tokens. Symmetric HS256 keeps key management to a
# single shared secret (AUTH_JWT_SECRET) — adequate for a first-party API issuing its own tokens.
_ALGORITHM = "HS256"


class TokenHelpers:
    """
    Static-only helpers for minting and verifying HS256 JWT access tokens.

    Tokens encode the user id as the ``sub`` claim plus standard ``iat`` / ``exp`` timestamps.
    The secret and lifetime are always supplied by the caller (AuthService reads them from
    RUNTIME_CONFIG) — this class never touches config so it stays trivially testable.
    """

    logger = loggerplusplus.bind(identifier="TokenHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TokenHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def mint(
        cls,
        *,
        subject: str,
        secret: str,
        ttl_minutes: int,
        extra_claims: dict | None = None,
    ) -> str:
        """
        Mint a signed JWT access token for a subject (user id).

        Args:
            subject (str): The token subject — the user's id (stringified UUID).
            secret (str): HS256 signing secret.
            ttl_minutes (int): Token lifetime in minutes.
            extra_claims (dict | None): Optional additional claims to embed (e.g. an
                ``impersonated_by`` audit claim). The reserved ``sub`` / ``iat`` / ``exp``
                claims are protected — any same-named key here is ignored, never overrides them.

        Returns:
            str: The encoded, signed JWT.
        """
        # 1. Build standard claims (issued-at + absolute expiry)
        now = datetime.now(timezone.utc)
        claims = {
            "sub": subject,
            "iat": now,
            "exp": now + timedelta(minutes=ttl_minutes),
        }

        # 2. Merge any extra claims WITHOUT letting them shadow the reserved standard claims
        #    (a caller-supplied "sub"/"exp" must never silently re-target or extend the token).
        if extra_claims:
            for key, value in extra_claims.items():
                if key not in claims:
                    claims[key] = value

        # 3. Encode + sign
        return jwt.encode(claims, secret, algorithm=_ALGORITHM)

    @classmethod
    def verify(cls, *, token: str, secret: str) -> dict | None:
        """
        Verify a JWT's signature + expiry and return its claims.

        Args:
            token (str): The encoded JWT to verify.
            secret (str): HS256 signing secret (must match the minting secret).

        Returns:
            dict | None: The decoded claims if valid, or None if the token is invalid/expired.
        """
        # 1. Decode with signature + expiry enforcement; any failure means "not a valid token"
        try:
            return jwt.decode(token, secret, algorithms=[_ALGORITHM])
        except jwt.PyJWTError:
            return None
