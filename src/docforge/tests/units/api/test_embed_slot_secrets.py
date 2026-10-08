"""Per-slot embed secrets: ``dense.api_key`` / ``sparse.api_key`` are masked on read and restored only
at the SAME slot endpoint; a not-yet-healed legacy stored node (``bge_server`` / ``openai_compatible``
with a top-level key) is the secret source of the migrated slots a client writes back
(``_as_slot_source``), never across an endpoint change.
"""

import pytest

from shared_libs.pipelines.blob_secrets import (
    MASK,
    SecretReentryRequired,
    _as_slot_source,
    redact_blob_secrets,
    restore_blob_secrets,
)

URL = "https://embed.example:443"
ATTACKER = "https://attacker.example"
KEY = "sk-EMBED-1111"


def _embed(kind: str, config: dict) -> dict:
    """A one-embed-node blob."""
    return {"nodes": [{"id": "embed", "family": "embed", "kind": kind, "config": config}]}


def _slot(kind: str, url: str, key: str | None) -> dict:
    """A provider slot (the key omitted when None)."""
    slot = {"kind": kind, "base_url": url}
    if key is not None:
        slot["api_key"] = key
    return slot


def _slots(blob: dict) -> dict:
    """The embed node's config."""
    return blob["nodes"][0]["config"]


def test_both_slot_keys_are_masked_on_read() -> None:
    stored = _embed(
        "dense_sparse",
        {"dense": _slot("openai_compatible", URL, KEY), "sparse": _slot("bge_server", URL, KEY)},
    )
    redacted = _slots(redact_blob_secrets(stored))
    assert redacted["dense"]["api_key"] == MASK
    assert redacted["sparse"]["api_key"] == MASK


def test_masked_slot_keys_restore_at_the_same_endpoint() -> None:
    stored = _embed(
        "dense_sparse",
        {"dense": _slot("bge_server", URL, KEY), "sparse": _slot("bge_server", URL, "sk-2")},
    )
    incoming = _embed(
        "dense_sparse",
        {"dense": _slot("bge_server", URL, MASK), "sparse": _slot("bge_server", URL, None)},
    )
    healed = _slots(restore_blob_secrets(incoming, stored))
    assert healed["dense"]["api_key"] == KEY
    assert healed["sparse"]["api_key"] == "sk-2"


def test_a_slot_endpoint_change_requires_the_key_again() -> None:
    stored = _embed("dense_sparse", {"dense": _slot("bge_server", URL, KEY), "sparse": None})
    incoming = _embed(
        "dense_sparse", {"dense": _slot("bge_server", ATTACKER, MASK), "sparse": None}
    )
    with pytest.raises(SecretReentryRequired):
        restore_blob_secrets(incoming, stored)


def test_legacy_stored_node_is_the_source_of_the_migrated_slots() -> None:
    stored = _embed("bge_server", {"base_url": URL, "api_key": KEY})
    incoming = _embed(
        "dense_sparse",
        {"dense": _slot("bge_server", URL, MASK), "sparse": _slot("bge_server", URL, MASK)},
    )
    healed = _slots(restore_blob_secrets(incoming, stored))
    assert healed["dense"]["api_key"] == KEY
    assert healed["sparse"]["api_key"] == KEY


def test_legacy_stored_key_never_follows_a_slot_to_another_host() -> None:
    stored = _embed("openai_compatible", {"base_url": URL, "api_key": KEY, "model": "m"})
    incoming = _embed(
        "dense_sparse", {"dense": _slot("openai_compatible", ATTACKER, MASK), "sparse": None}
    )
    with pytest.raises(SecretReentryRequired):
        restore_blob_secrets(incoming, stored)


def test_as_slot_source_only_maps_a_legacy_embed_source_under_a_slot_node() -> None:
    slot_node = {"id": "embed", "family": "embed", "kind": "dense_sparse"}
    legacy = ("embed", "bge_server", {"base_url": URL, "api_key": KEY, "embed_sparse": False})

    family, kind, config = _as_slot_source(slot_node, legacy)
    assert (family, kind) == ("embed", "dense_sparse")
    assert config["dense"] == {"kind": "bge_server", "base_url": URL, "api_key": KEY}
    assert config["sparse"] is None

    # No source, a non-legacy source, or a non-slot inbound node: passed through untouched.
    assert _as_slot_source(slot_node, None) is None
    current = ("embed", "dense_sparse", {"dense": None})
    assert _as_slot_source(slot_node, current) is current
    legacy_node = {"id": "embed", "family": "embed", "kind": "bge_server"}
    assert _as_slot_source(legacy_node, legacy) is legacy
    foreign = ("llm", "bge_server", {})
    assert _as_slot_source(slot_node, foreign) is foreign
