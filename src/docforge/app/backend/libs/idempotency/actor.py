# ====== Code Summary ======
# IdempotencyActorScope — distils the authenticated principal into the NEVER-NULL ``actor_scope``
# string that scopes an idempotency record, so one tenant's key never dedups against another's. A key
# → "key:<uuid>", a user without a key → "user:<uuid>", and the auth-off synthetic root (no rows) →
# the literal "anon". A NULL scope would let Postgres treat rows as distinct in the UNIQUE guard and
# defeat dedup, so the value is always a concrete string.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from ..auth import AuthPrincipal

# The scope used when there is no backing identity (auth disabled → the synthetic root principal).
_ANON_SCOPE = "anon"


class IdempotencyActorScope:
    """Static helper mapping an auth principal to its never-null idempotency actor scope."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IdempotencyActorScope is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve(principal: AuthPrincipal | None) -> str:
        """
        Resolve the never-null ``actor_scope`` for an idempotency record.

        Args:
            principal (AuthPrincipal | None): The principal the authN middleware injected, or None
                when it did not run (defensive — an eligible /api/v1 request always has one).

        Returns:
            str: ``"key:<uuid>"`` for an authenticated key, ``"user:<uuid>"`` for a keyless user, or
                ``"anon"`` when there is no backing identity (auth off / synthetic root / no principal).
        """
        # 1. No principal at all → anonymous (defensive; /api/v1 always carries one).
        if principal is None:
            return _ANON_SCOPE
        # 2. An authenticated key is the strongest identity — scope per key.
        if principal.key is not None:
            return f"key:{principal.key.id}"
        # 3. A user without a key (rare) still scopes per account.
        if principal.user is not None:
            return f"user:{principal.user.id}"
        # 4. The auth-off synthetic root has no rows → a single shared anonymous scope.
        return _ANON_SCOPE


__all__ = ["IdempotencyActorScope"]
