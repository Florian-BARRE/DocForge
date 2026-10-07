# ====== Code Summary ======
# SnapshotSecretResolver — the secret rule of a config-version RESTORE. A stored snapshot holds REAL
# secrets, but restoring it must neither resurrect a rotated key nor carry a key across endpoints:
#   1. the snapshot is masked, then healed against the CURRENT blob through the PATCH rule
#      (restore_blob_secrets): the same provider at the same endpoint keeps the CURRENT key (a key
#      rotated since the snapshot is never rolled back), and a provider whose current key lives at a
#      DIFFERENT endpoint than the snapshot's raises SecretReentryRequired (→ 422, re-enter the key with
#      a PATCH) — the operator moved away from that host, so its old key is never silently re-sent;
#   2. a secret that heal left blank because the CURRENT blob has no key for that provider (the node
#      was removed or re-kinded since, or its key cleared) falls back to the snapshot's OWN stored key.
#      That key was stored paired with that very endpoint and the pairing is restored unchanged, so
#      nothing is carried to a new host — while blanking it would silently persist a keyless provider.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import (
    is_masked,
    redact_blob_secrets,
    restore_blob_secrets,
)


class SnapshotSecretResolver:
    """Static secret resolution of a stored snapshot blob being restored over the current blob."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SnapshotSecretResolver is a static-only class and cannot be instantiated.")

    @classmethod
    def resolve(cls, snapshot: dict | None, current: dict | None) -> dict | None:
        """
        Resolve the secrets of a snapshot blob about to be written back as the current config.

        Args:
            snapshot (dict | None): The stored snapshot's pipeline or search blob (real secrets).
            current (dict | None): The collection's current blob of the same kind (real secrets).

        Returns:
            dict | None: The snapshot blob with every secret resolved (current key, else its own).

        Raises:
            SecretReentryRequired: When a provider's current key lives at another endpoint.
        """
        # 1. The PATCH rule over the masked snapshot: current same-endpoint keys win, a moved endpoint
        #    is refused (raises), a provider without a current key comes back blank.
        masked = redact_blob_secrets(snapshot)
        healed = restore_blob_secrets(masked, current)
        # 2. Refill each blanked mask with the snapshot's own key at the same position (same endpoint).
        return cls._backfill(healed, masked, snapshot)

    @classmethod
    def _backfill(cls, healed: Any, masked: Any, original: Any) -> Any:
        """Walk the three same-shaped trees; a mask healed to "" takes the snapshot's real value."""
        # 1. A masked leaf the heal blanked → the snapshot's own live key (never a stale mask).
        if is_masked(masked) and healed == "":
            real = isinstance(original, str) and original != "" and not is_masked(original)
            return original if real else healed
        # 2. Containers recurse position by position (masking/healing never change the shape).
        if isinstance(healed, dict) and isinstance(masked, dict) and isinstance(original, dict):
            return {k: cls._backfill(v, masked.get(k), original.get(k)) for k, v in healed.items()}
        if isinstance(healed, list) and isinstance(masked, list) and isinstance(original, list):
            if len(healed) == len(masked) == len(original):
                return [
                    cls._backfill(*triple) for triple in zip(healed, masked, original, strict=True)
                ]
        return healed


__all__ = ["SnapshotSecretResolver"]
