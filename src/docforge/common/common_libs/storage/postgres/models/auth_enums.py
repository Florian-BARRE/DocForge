# ====== Code Summary ======
# String enumeration for the authentication layer.
# Defines the allowed values for the global user-role column. The DB column itself stays plain
# VARCHAR — this enum is the single source of truth for the legal string values in Python code.
# (Per-collection authorization is no longer a stored role: it is the capability scope carried on
# API keys — see backend.libs.auth.capabilities.)

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """
    Global role of an application user.

    In the keys-only model the only login account is root; ``USER`` is retained for schema /
    backward-compatibility on the ``app_user.role`` column.

    Attributes:
        ROOT: Superuser — full administrative access across the whole instance.
        USER: Standard user (legacy / non-login).
    """

    ROOT = "root"
    USER = "user"
