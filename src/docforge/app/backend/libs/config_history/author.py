# ====== Code Summary ======
# ConfigAuthorResolver — distils the request principal into the author stamped on a config version:
# the API key's id + "<name> (<prefix>)", the owning username for a key-less principal, or "anonymous"
# for the synthetic auth-off principal (no rows exist to name it). The key PREFIX makes the label
# unforgeable by a key merely NAMED like another (and key creation refuses the reserved names "root" /
# "anonymous"); the bootstrap root key is named "root", so a root-token write reads "root (df_…)".
# Read-only use of the auth principal.

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import ConfigAuthor

# ====== Local Project Imports ======
from ..auth import AuthPrincipal

# The label of a write made while authentication is disabled (synthetic principal, no key, no user).
ANONYMOUS_LABEL = "anonymous"

# The author_label column width — a longer key name is truncated, never a write failure.
_LABEL_MAX_LENGTH = 255


class ConfigAuthorResolver:
    """Static principal → ConfigAuthor mapping for the config-history write sites."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigAuthorResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def from_principal(principal: AuthPrincipal) -> ConfigAuthor:
        """
        Build the config-version author of a request.

        Args:
            principal (AuthPrincipal): The authenticated caller (synthetic when auth is off).

        Returns:
            ConfigAuthor: The key id (None without a key) and a human-readable label.
        """
        # 1. A key-authenticated caller is named by its key + prefix (the root key is named "root").
        if principal.key is not None:
            label = f"{principal.key.name} ({principal.key.prefix})"
            return ConfigAuthor(key_id=principal.key.id, label=label[:_LABEL_MAX_LENGTH])
        # 2. A key-less principal with a user row, else the auth-off synthetic principal.
        if principal.user is not None:
            return ConfigAuthor(key_id=None, label=principal.user.username[:_LABEL_MAX_LENGTH])
        return ConfigAuthor(key_id=None, label=ANONYMOUS_LABEL)


__all__ = ["ANONYMOUS_LABEL", "ConfigAuthorResolver"]
