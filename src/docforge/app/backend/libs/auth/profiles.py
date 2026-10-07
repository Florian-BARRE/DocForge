# ====== Code Summary ======
# Named usage profiles — presets that expand to an explicit capability list at key creation/rotation.
# The STORED form of a key is always the explicit list (the profile name rides along for display
# only), so a profile is a convenience, never a second source of truth. `match` recovers the profile
# of a key created with an explicit list that happens to equal a preset (legacy / hand-built keys).

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum

# ====== Local Project Imports ======
from .capability import CANONICAL_CAPABILITIES, Capability


class KeyProfile(StrEnum):
    """A named preset of capabilities offered at key creation."""

    # A business chatbot: reads documents as text and searches — no internals.
    AGENT_READER = "agent_reader"
    # The narrowest retrieval key: search only (hits already carry the chunk text).
    AGENT_SEARCHER = "agent_searcher"
    # An operator: full read (text + technical) and write, no key management.
    OPERATOR = "operator"
    # Every capability, still bounded by the key's collection scope (unlike a NULL-permission root).
    ADMIN = "admin"


class KeyProfiles:
    """Static helpers mapping a profile to its capability preset and back."""

    _PRESETS: dict[KeyProfile, tuple[Capability, ...]] = {
        KeyProfile.AGENT_READER: (Capability.READ_TEXT, Capability.SEARCH),
        KeyProfile.AGENT_SEARCHER: (Capability.SEARCH,),
        KeyProfile.OPERATOR: (Capability.READ_TEXT, Capability.READ_TECHNICAL, Capability.WRITE),
        KeyProfile.ADMIN: CANONICAL_CAPABILITIES,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("KeyProfiles is a static-only class and cannot be instantiated.")

    @classmethod
    def capabilities_of(cls, profile: KeyProfile) -> list[Capability]:
        """
        Expand a profile into its explicit capability list.

        Args:
            profile (KeyProfile): The named preset.

        Returns:
            list[Capability]: The capabilities the preset grants, in declaration order.
        """
        # 1. A fresh list so callers can never mutate the preset table.
        return list(cls._PRESETS[profile])

    @classmethod
    def match(cls, capabilities: list[Capability]) -> KeyProfile | None:
        """
        Recover the profile whose preset equals an explicit capability set, if any.

        Args:
            capabilities (list[Capability]): A key's (normalized) capabilities.

        Returns:
            KeyProfile | None: The matching profile, or None for a custom combination.
        """
        # 1. Order-insensitive exact-set comparison against every preset.
        wanted = set(capabilities)
        for profile, preset in cls._PRESETS.items():
            if set(preset) == wanted:
                return profile
        return None


__all__ = ["KeyProfile", "KeyProfiles"]
