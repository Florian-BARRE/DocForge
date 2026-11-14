# ====== Code Summary ======
# Public facade of the blob secret redaction — the function names the app (config-history, collection
# routers, snippets) and the worker (export bundle) import. The logic lives in the ``BlobSecrets`` class
# (``shared_libs.pipelines.secrets``); each function here only delegates, so the API surface and the
# export surface keep ONE definition of what counts as a secret and how it is masked / restored.

# ====== Internal Project Imports ======
from shared_libs.pipelines.secret_identity import SECRET_FIELDS
from shared_libs.pipelines.secrets import MASK, MASK_PREFIX, BlobSecrets, SecretReentryRequired


def is_masked(value: object) -> bool:
    """True when a value is a redaction marker — the current constant OR the legacy last-4 form."""
    return BlobSecrets.is_masked(value)


def has_blob_secrets(blob: dict | None) -> bool:
    """Return whether any action node in a blob carries a non-empty provider secret field.

    See ``BlobSecrets.has_secrets``.
    """
    return BlobSecrets.has_secrets(blob)


def redact_blob_secrets(blob: dict | None) -> dict | None:
    """Return a deep copy of a pipeline/search blob with every provider secret masked.

    See ``BlobSecrets.redact``.
    """
    return BlobSecrets.redact(blob)


def redact_config_snapshot(config: dict | None) -> dict | None:
    """Return a masked copy of an archived config-version snapshot ``{"pipeline": …, "search": …}``.

    See ``BlobSecrets.redact_snapshot``.
    """
    return BlobSecrets.redact_snapshot(config)


def restore_blob_secrets(incoming: dict | None, stored: dict | None) -> dict | None:
    """Return a deep copy of an inbound blob with its secrets healed back to the stored keys.

    See ``BlobSecrets.restore``.

    Raises:
        SecretReentryRequired: When a masked/omitted secret's provider endpoint changed, or a nested
            override relies on an inherited key at a foreign endpoint.
    """
    return BlobSecrets.restore(incoming, stored)


# Kept importable under its historical private name (pinned by test_embed_slot_secrets).
_as_slot_source = BlobSecrets.as_slot_source


__all__ = [
    "SECRET_FIELDS",
    "MASK_PREFIX",
    "MASK",
    "SecretReentryRequired",
    "is_masked",
    "has_blob_secrets",
    "redact_blob_secrets",
    "redact_config_snapshot",
    "restore_blob_secrets",
]
