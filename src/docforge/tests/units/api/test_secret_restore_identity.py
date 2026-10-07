"""restore_blob_secrets identity rule: an OMITTED secret on the same node id AND kind is kept, an
explicit "" clears it, a kind mismatch never restores, a chain reorder never cross-restores (a
same-kind sibling at the same endpoint is the source; a different kind never is), and an endpoint
change never carries the stored key — a masked/omitted secret there is refused (SecretReentryRequired)."""

import pytest

from shared_libs.pipelines.blob_secrets import MASK, SecretReentryRequired, restore_blob_secrets


def _node(node_id: str, kind: str, **config) -> dict:
    return {"id": node_id, "family": "ocr", "kind": kind, "config": dict(config)}


def _blob(*nodes: dict) -> dict:
    return {"nodes": list(nodes)}


def _config(blob: dict, node_id: str) -> dict:
    return next(n for n in blob["nodes"] if n["id"] == node_id)["config"]


STORED = _blob(
    _node("chain_0", "mistral", api_key="sk-mistral"),
    _node("chain_1", "openai_compatible", base_url="https://a.example/v1", api_key="sk-a"),
)


def test_omitted_secret_is_kept_on_same_id_and_kind() -> None:
    healed = restore_blob_secrets(_blob(_node("chain_0", "mistral")), STORED)
    assert _config(healed, "chain_0")["api_key"] == "sk-mistral"


def test_explicit_empty_string_clears() -> None:
    healed = restore_blob_secrets(_blob(_node("chain_0", "mistral", api_key="")), STORED)
    assert _config(healed, "chain_0")["api_key"] == ""


def test_kind_mismatch_never_restores() -> None:
    incoming = _blob(
        _node("chain_0", "openai_compatible"), _node("chain_1", "rapidocr", api_key=MASK)
    )
    healed = restore_blob_secrets(incoming, STORED)
    assert "api_key" not in _config(healed, "chain_0")
    assert _config(healed, "chain_1")["api_key"] == ""


def test_reorder_of_different_kinds_restores_each_provider_its_own_key() -> None:
    incoming = _blob(
        _node("chain_0", "openai_compatible", base_url="https://a.example/v1", api_key=MASK),
        _node("chain_1", "mistral", api_key=MASK),
    )
    healed = restore_blob_secrets(incoming, STORED)
    assert _config(healed, "chain_0")["api_key"] == "sk-a"  # sibling, same kind + endpoint
    assert _config(healed, "chain_1")["api_key"] == ""  # mistral moved, no endpoint: never cross


def test_reorder_of_same_kind_providers_follows_the_endpoint() -> None:
    stored = _blob(
        _node("c_0", "openai_compatible", base_url="https://a.example", api_key="sk-a"),
        _node("c_1", "openai_compatible", base_url="https://b.example", api_key="sk-b"),
    )
    incoming = _blob(
        _node("c_0", "openai_compatible", base_url="https://b.example"),
        _node("c_1", "openai_compatible", base_url="https://a.example", api_key=MASK),
    )
    healed = restore_blob_secrets(incoming, stored)
    assert _config(healed, "c_0")["api_key"] == "sk-b"
    assert _config(healed, "c_1")["api_key"] == "sk-a"


def test_endpoint_edited_in_place_is_refused_never_carried() -> None:
    # The old rule carried the stored key onto the edited endpoint — an exfiltration path.
    incoming = _blob(_node("chain_1", "openai_compatible", base_url="https://evil.example/v1"))
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, STORED)
    assert caught.value.fields == [("chain_1", "api_key")]
    assert "sk-a" not in str(caught.value)


def test_masked_secret_on_an_edited_endpoint_is_refused() -> None:
    incoming = _blob(
        _node("chain_1", "openai_compatible", base_url="https://evil.example/v1", api_key=MASK)
    )
    with pytest.raises(SecretReentryRequired):
        restore_blob_secrets(incoming, STORED)


def test_edited_endpoint_with_a_new_key_or_a_clear_is_accepted() -> None:
    for value in ("sk-new", ""):
        incoming = _blob(
            _node("chain_1", "openai_compatible", base_url="https://evil.example/v1", api_key=value)
        )
        assert _config(restore_blob_secrets(incoming, STORED), "chain_1")["api_key"] == value


def test_endpoint_spelling_variants_are_the_same_endpoint() -> None:
    incoming = _blob(_node("chain_1", "openai_compatible", base_url="HTTPS://A.EXAMPLE:443/v1/"))
    assert _config(restore_blob_secrets(incoming, STORED), "chain_1")["api_key"] == "sk-a"


def test_omitted_and_explicit_default_endpoint_are_the_same_endpoint() -> None:
    # (ocr, mistral) defaults base_url to https://api.mistral.ai/v1.
    explicit = _blob(_node("chain_0", "mistral", base_url="https://api.mistral.ai/v1/"))
    assert _config(restore_blob_secrets(explicit, STORED), "chain_0")["api_key"] == "sk-mistral"
    stored_explicit = _blob(
        _node("chain_0", "mistral", base_url="https://api.mistral.ai/v1", api_key="sk-m")
    )
    omitted = _blob(_node("chain_0", "mistral"))
    assert _config(restore_blob_secrets(omitted, stored_explicit), "chain_0")["api_key"] == "sk-m"


def test_chain_reorder_onto_a_different_host_never_carries() -> None:
    stored = _blob(
        _node("c_0", "openai_compatible", base_url="https://a.example", api_key="sk-a"),
        _node("c_1", "openai_compatible", base_url="https://b.example", api_key="sk-b"),
    )
    incoming = _blob(
        _node("c_0", "openai_compatible", base_url="https://b.example"),
        _node("c_1", "openai_compatible", base_url="https://evil.example"),
    )
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, stored)
    assert caught.value.fields == [("c_1", "api_key")]
