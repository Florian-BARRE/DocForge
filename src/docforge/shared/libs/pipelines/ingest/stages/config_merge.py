# ====== Code Summary ======
# StageConfigMerge — resolves the config a set_config action lands on a node from the node's CURRENT
# config, the action's patch and its mode. ``replace`` is the historical whole-dict replacement;
# ``merge`` overlays the patch on the current config, an explicit ``None`` deleting the key so the node
# falls back to its schema default — except on a secret field, where ``None`` is an explicit CLEAR
# (``""``): a deleted secret reads as "omitted" and the write path would restore the stored key. A
# merge that MOVES the endpoint (``base_url``) drops every secret the patch does not restate — including
# a nested one (a metagen target without its own base_url follows the node's endpoint) — so the current
# key is never re-pointed at the new host (the write path then demands re-entry). Kept out of
# the compiler so every set_config branch (intake, convert, chain head, single-config stage) resolves
# through the ONE rule.

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Internal Project Imports ======
from shared_libs.pipelines.nested_secrets import NestedSecrets
from shared_libs.pipelines.secret_identity import ENDPOINT_FIELD, SECRET_FIELDS, SecretIdentity

# The two ways a set_config patch lands on a node's current config.
type ConfigMode = Literal["replace", "merge"]


class StageConfigMerge:
    """Static resolver of a set_config patch against a node's current config."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageConfigMerge is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve(
        current: dict[str, Any] | None, patch: dict[str, Any], mode: ConfigMode
    ) -> dict[str, Any]:
        """
        The config to store on the node after a set_config.

        Args:
            current (dict | None): The node's current config (``None`` when it has none yet).
            patch (dict): The action's config dict.
            mode (ConfigMode): ``replace`` = the patch IS the new config (verbatim, as before);
                ``merge`` = ``{**current, **patch}`` where a ``None`` value deletes the key (a
                ``None`` secret becomes ``""``), and an endpoint change drops the unrestated secrets.

        Returns:
            dict: A fresh dict — never aliases ``current`` or ``patch``.
        """
        # 1. Replace keeps the historical whole-dict semantics byte-for-byte.
        if mode == "replace":
            return dict(patch)

        # 2. Merge overlays the patch; an explicit null removes the key (back to the schema default),
        #    but clears a secret — a removed secret would read as omitted and be restored.
        merged = dict(current or {})
        for key, value in patch.items():
            if value is None and key in SECRET_FIELDS:
                merged[key] = ""
            elif value is None:
                merged.pop(key, None)
            else:
                merged[key] = value

        # 3. A moved endpoint never keeps the current secret the patch did not restate — neither the
        #    top-level one nor a nested one whose item follows the node's endpoint (no own base_url).
        if ENDPOINT_FIELD in patch and SecretIdentity.endpoint(current) != SecretIdentity.endpoint(
            merged
        ):
            for field in SECRET_FIELDS - patch.keys():
                merged.pop(field, None)
            NestedSecrets.drop_inherited(merged, set(patch))
        return merged


__all__ = ["ConfigMode", "StageConfigMerge"]
