# ====== Code Summary ======
# AuditHelpers — the pure decision + extraction helpers the audit middleware leans on: which requests
# are auditable (mutating verbs on /api/v1 only), and the actor identity fields distilled from the
# authenticated principal (user id / key id / a human-readable label). Kept separate from the
# middleware so the ASGI plumbing stays thin and these rules are unit-testable in isolation.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from dataclasses import dataclass

# ====== Local Project Imports ======
from ..auth import AuthPrincipal
from .read_exclusion import AuditReadExclusion

# Only these verbs mutate state and are therefore audited; reads (GET/HEAD/OPTIONS) are skipped.
_MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Only the API surface is audited; everything else (docs, /metrics, health, static UI) is skipped.
_API_PREFIX = "/api/v1"

# The actor label used for the auth-off synthetic root (no user/key rows exist to name it).
_ROOT_LABEL = "root"


@dataclass(frozen=True, slots=True)
class AuditActor:
    """
    The distilled actor identity for one audit row.

    Attributes:
        user_id (uuid.UUID | None): The acting user's id, when known.
        key_id (uuid.UUID | None): The acting API key's id, when known.
        label (str | None): A human-readable label (key name / username / "root").
    """

    user_id: uuid.UUID | None
    key_id: uuid.UUID | None
    label: str | None


class AuditHelpers:
    """Static helpers for the audit middleware's applicability + actor-extraction rules."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuditHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_auditable(method: str, path: str) -> bool:
        """
        Decide whether a request must be recorded in the audit trail.

        Args:
            method (str): The request's HTTP method.
            path (str): The request path (``scope["path"]``).

        Returns:
            bool: True only for a mutating request on the ``/api/v1`` surface — a read verb, a
                non-API path, or a POST-shaped READ endpoint (search / query / estimate / pipeline
                design) all return False (reads are never audited, whatever their verb).
        """
        # 1. Read verbs never mutate → never audited.
        if method not in _MUTATING_METHODS:
            return False
        # 2. Only the API surface carries auditable actions.
        if not path.startswith(_API_PREFIX):
            return False
        # 3. A handful of genuinely read-only endpoints are exposed over POST (they need a JSON body):
        #    honour the "reads are never audited" contract by excluding them explicitly.
        return not AuditReadExclusion.is_read(path)

    @staticmethod
    def actor(principal: AuthPrincipal | None) -> AuditActor:
        """
        Distil the actor identity fields from the authenticated principal.

        Args:
            principal (AuthPrincipal | None): The principal the authN middleware injected, or None
                when it did not run (should not happen on an audited /api/v1 request).

        Returns:
            AuditActor: The user id, key id, and a human-readable label (best-effort).
        """
        # 1. No principal → an unattributable action (defensive; /api/v1 always has one).
        if principal is None:
            return AuditActor(user_id=None, key_id=None, label=None)

        # 2. Pull the raw ids off the backing rows (either may be absent for the synthetic root).
        user_id = principal.user.id if principal.user is not None else None
        key_id = principal.key.id if principal.key is not None else None

        # 3. Label preference: the key's name, else the user's username, else "root" (auth-off).
        if principal.key is not None:
            label: str | None = principal.key.name
        elif principal.user is not None:
            label = principal.user.username
        else:
            label = _ROOT_LABEL
        return AuditActor(user_id=user_id, key_id=key_id, label=label)


__all__ = ["AuditActor", "AuditHelpers"]
