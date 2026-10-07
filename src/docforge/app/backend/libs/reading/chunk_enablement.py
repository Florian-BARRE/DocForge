# ====== Code Summary ======
# ChunkEnablement — a chunk's EFFECTIVE searchability from its two stored inputs: the user override
# wins, else the single role→default policy (role_default_enabled). The role column is a plain VARCHAR,
# so an unknown (forward-compat / legacy) value degrades to "disabled" instead of failing the read.
# Shared by the explorer chunk mapping and the context window's disabled-neighbour skip.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import ChunkRole, role_default_enabled


class ChunkEnablement:
    """Resolve a chunk's effective enabled state (override ?? role default)."""

    logger = loggerplusplus.bind(identifier="ChunkEnablement")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChunkEnablement is a static-only class and cannot be instantiated.")

    @classmethod
    def effective(cls, role: str, enabled_override: bool | None, chunk_ref: object = None) -> bool:
        """
        Return whether a chunk is searchable.

        Args:
            role (str): The stored structural role value.
            enabled_override (bool | None): The user's override (None = defer to the role).
            chunk_ref (object): The chunk id, used only to name the chunk in a degradation warning.

        Returns:
            bool: The override when set, else the role's default (False for an unknown role).
        """
        # 1. An explicit user override always wins over the structural default.
        if enabled_override is not None:
            return enabled_override

        # 2. No override — the single role policy; an unknown stored role degrades to disabled.
        try:
            chunk_role = ChunkRole(role)
        except ValueError:
            cls.logger.warning(
                f"Unknown chunk role '{role}' on chunk {chunk_ref}; defaulting to disabled"
            )
            return False
        return role_default_enabled(chunk_role)


__all__ = ["ChunkEnablement"]
