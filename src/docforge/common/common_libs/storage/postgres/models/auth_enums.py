# ====== Code Summary ======
# String enumerations for the authentication / authorization layer.
# These define the allowed values for the two role columns (global user role and
# per-collection grant role). The DB columns themselves stay plain VARCHAR — these
# enums are the single source of truth for the legal string values in Python code.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """
    Global role of an application user.

    Attributes:
        ROOT: Superuser — full administrative access across the whole instance.
        USER: Standard user — access is scoped by per-collection grants.
    """

    ROOT = "root"
    USER = "user"


class GrantRole(StrEnum):
    """
    Per-collection role granted to a user (GitHub-collaborator model).

    Ordered from least to most privileged: a higher role implies the capabilities
    of the lower ones (enforcement lives in the later auth layer, not here).

    Attributes:
        READ: May read/search the collection and its documents.
        WRITE: READ + ingest/update/delete documents in the collection.
        ADMIN: WRITE + manage the collection's settings and its collaborators.
    """

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
