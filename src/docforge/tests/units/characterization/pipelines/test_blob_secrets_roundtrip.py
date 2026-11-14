# ====== Code Summary ======
# Characterization of the blob-secrets public surface (safety net for turning blob_secrets.py into the
# BlobSecrets class behind a function facade, R-16). It pins TODAY's behaviour of ``redact_blob_secrets`` /
# ``redact_config_snapshot`` / ``restore_blob_secrets`` / ``has_blob_secrets`` / ``is_masked`` and the
# ``SecretReentryRequired`` refusal over representative blobs: groups and foreach bodies, an OCR chain
# reordered and an endpoint edited in place, nested metagen target keys, legacy embed slots, and the
# redact → restore round-trip. A drift is a refactoring decision to review, never a test to fix.

# ====== Standard Library Imports ======
import copy

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import (
    MASK,
    MASK_PREFIX,
    SECRET_FIELDS,
    SecretReentryRequired,
    has_blob_secrets,
    is_masked,
    redact_blob_secrets,
    redact_config_snapshot,
    restore_blob_secrets,
)

NODE_URL = "https://llm.example/v1"
ATTACKER = "https://attacker.example/v1"
KEY = "sk-NODE-1111"
TARGET_KEY = "sk-TARGET-2222"


def _node(node_id: str, family: str, kind: str, **config: object) -> dict:
    """One action node."""
    return {"id": node_id, "family": family, "kind": kind, "config": dict(config)}


def _config(blob: dict, node_id: str) -> dict:
    """The config of the first node (walked through groups and foreach bodies) with that id."""

    def walk(nodes: list) -> dict | None:
        for node in nodes:
            if node.get("id") == node_id:
                return node["config"]
            found = walk(node.get("nodes") or []) or walk(
                (node.get("body") or {}).get("nodes") or []
            )
            if found is not None:
                return found
        return None

    found = walk(blob["nodes"])
    assert found is not None, node_id
    return found


def _chain_blob() -> dict:
    """A group holding an OCR chain (two same-kind openai_compatible steps + mistral) and a foreach."""
    return {
        "id": "root",
        "kind": "group",
        "nodes": [
            {
                "id": "chain",
                "kind": "group",
                "nodes": [
                    _node(
                        "ocr_0",
                        "ocr",
                        "openai_compatible",
                        base_url="https://a.example",
                        api_key="sk-a",  # pragma: allowlist secret
                    ),
                    _node(
                        "ocr_1",
                        "ocr",
                        "openai_compatible",
                        base_url="https://b.example",
                        api_key="sk-b",  # pragma: allowlist secret
                    ),
                    _node(
                        "ocr_2",
                        "ocr",
                        "mistral",
                        api_key="sk-mistral",  # pragma: allowlist secret
                    ),  # pragma: allowlist secret
                ],
            },
            {
                "id": "loop",
                "kind": "foreach",
                "body": {
                    "nodes": [
                        _node(
                            "gen_0",
                            "structgen",
                            "openai_compatible",
                            base_url=NODE_URL,
                            api_key=KEY,
                        )
                    ]
                },
            },
            _node(
                "gotenberg",
                "convert",
                "gotenberg",
                base_url="http://gotenberg:3000",
                password="pw",  # pragma: allowlist secret
            ),
        ],
    }


def _metagen_blob() -> dict:
    """A metagen prep keyed at NODE_URL with one nested target keyed at its own endpoint."""
    return {
        "nodes": [
            _node(
                "prep",
                "metagen",
                "document_prep",
                base_url=NODE_URL,
                api_key=KEY,
                model="m",
                targets=[
                    {"field": "summary", "base_url": ATTACKER, "api_key": TARGET_KEY},
                    {"field": "topic"},
                ],
            )
        ]
    }


# ─────────────────────────── redact ───────────────────────────


def test_public_constants_and_secret_fields() -> None:
    assert MASK == MASK_PREFIX == "__redacted__"
    assert set(SECRET_FIELDS) == {"api_key", "password"}


def test_redact_masks_every_secret_through_groups_and_foreach_bodies() -> None:
    stored = _chain_blob()
    original = copy.deepcopy(stored)
    masked = redact_blob_secrets(stored)

    assert stored == original  # the input is never mutated
    assert masked is not stored
    assert _config(masked, "ocr_0") == {"base_url": "https://a.example", "api_key": MASK}
    assert _config(masked, "ocr_1")["api_key"] == MASK
    assert _config(masked, "ocr_2") == {"api_key": MASK}
    assert _config(masked, "gen_0") == {"base_url": NODE_URL, "api_key": MASK}
    assert _config(masked, "gotenberg") == {"base_url": "http://gotenberg:3000", "password": MASK}
    assert "sk-" not in str(masked) and "pw" not in str(_config(masked, "gotenberg").values())


def test_redact_keeps_blank_and_non_string_values_and_never_adds_a_field() -> None:
    blob = {
        "nodes": [
            _node("a", "ocr", "mistral", api_key=""),
            _node("b", "ocr", "mistral", api_key=None),
            _node("c", "ocr", "mistral"),
            _node("d", "ocr", "mistral", api_key=12),
        ]
    }
    masked = redact_blob_secrets(blob)
    assert masked == blob
    assert "api_key" not in _config(masked, "c")


def test_redact_passes_a_non_dict_through_untouched() -> None:
    assert redact_blob_secrets(None) is None
    assert redact_blob_secrets({}) == {}
    marker = ["not", "a", "dict"]
    assert redact_blob_secrets(marker) is marker  # type: ignore[arg-type]


def test_redact_masks_a_nested_target_key_but_not_an_absent_one() -> None:
    masked = redact_blob_secrets(_metagen_blob())
    config = _config(masked, "prep")
    assert config["api_key"] == MASK
    assert config["targets"] == [
        {"field": "summary", "base_url": ATTACKER, "api_key": MASK},
        {"field": "topic"},
    ]


def test_redact_snapshot_wraps_pipeline_and_search_and_keeps_other_keys() -> None:
    snapshot = {"pipeline": _chain_blob(), "search": _metagen_blob(), "note": {"api_key": "kept"}}
    masked = redact_config_snapshot(snapshot)

    assert masked is not snapshot
    assert "sk-" not in str(masked["pipeline"]) and "sk-" not in str(masked["search"])
    assert _config(masked["pipeline"], "ocr_0")["api_key"] == MASK
    assert _config(masked["search"], "prep")["targets"][0]["api_key"] == MASK
    assert masked["note"] == {"api_key": "kept"}  # pragma: allowlist secret
    assert snapshot["pipeline"] == _chain_blob()
    assert redact_config_snapshot(None) is None
    assert redact_config_snapshot({"pipeline": None, "x": 1}) == {"pipeline": None, "x": 1}


def test_has_blob_secrets() -> None:
    assert has_blob_secrets(_chain_blob())
    assert has_blob_secrets(_metagen_blob())
    nested_only = {
        "nodes": [_node("p", "metagen", "document_prep", targets=[{"field": "s", "api_key": "k"}])]
    }
    assert has_blob_secrets(nested_only)
    assert not has_blob_secrets(
        redact_blob_secrets({"nodes": [_node("a", "ocr", "mistral", api_key="")]})
    )
    assert not has_blob_secrets(
        {"nodes": [_node("a", "ocr", "mistral", api_key="", password=None)]}
    )
    assert (
        not has_blob_secrets(None)
        and not has_blob_secrets({})
        and not has_blob_secrets({"nodes": "x"})
    )


def test_is_masked_accepts_the_constant_and_the_legacy_last4_form() -> None:
    assert is_masked(MASK) and is_masked(MASK + "abcd")
    assert (
        not is_masked("sk-real") and not is_masked("") and not is_masked(None) and not is_masked(3)
    )


# ─────────────────────────── restore ───────────────────────────


def test_restore_passes_a_non_dict_through() -> None:
    assert restore_blob_secrets(None, {}) is None
    marker = ["x"]
    assert restore_blob_secrets(marker, {}) is marker  # type: ignore[arg-type]


def test_round_trip_of_the_masked_blob_restores_every_key_without_mutation() -> None:
    stored = _chain_blob()
    incoming = redact_blob_secrets(stored)
    incoming_before = copy.deepcopy(incoming)

    healed = restore_blob_secrets(incoming, stored)

    assert healed == stored
    assert incoming == incoming_before
    assert healed is not incoming


def test_round_trip_of_nested_target_keys_survives_a_target_reorder() -> None:
    stored = _metagen_blob()
    incoming = redact_blob_secrets(stored)
    _config(incoming, "prep")["targets"].reverse()

    healed = _config(restore_blob_secrets(incoming, stored), "prep")

    assert healed["api_key"] == KEY
    assert {t["field"]: t.get("api_key") for t in healed["targets"]} == {
        "summary": TARGET_KEY,
        "topic": None,
    }


def test_omitted_secret_is_kept_explicit_empty_clears_a_new_key_is_verbatim() -> None:
    stored = _chain_blob()
    incoming = redact_blob_secrets(stored)
    del _config(incoming, "ocr_2")["api_key"]  # omitted
    _config(incoming, "ocr_0")["api_key"] = ""  # cleared
    _config(incoming, "ocr_1")["api_key"] = "sk-new"  # genuinely new  # pragma: allowlist secret

    healed = restore_blob_secrets(incoming, stored)

    assert _config(healed, "ocr_2")["api_key"] == "sk-mistral"  # pragma: allowlist secret
    assert _config(healed, "ocr_0")["api_key"] == ""
    assert _config(healed, "ocr_1")["api_key"] == "sk-new"  # pragma: allowlist secret


def test_chain_reorder_of_same_kind_steps_follows_the_endpoint() -> None:
    stored = _chain_blob()
    incoming = redact_blob_secrets(stored)
    chain = incoming["nodes"][0]["nodes"]
    # swap the two openai_compatible steps' positions (ids stay positional, configs move)
    chain[0]["config"], chain[1]["config"] = chain[1]["config"], chain[0]["config"]

    healed = restore_blob_secrets(incoming, stored)

    assert _config(healed, "ocr_0") == {
        "base_url": "https://b.example",
        "api_key": "sk-b",  # pragma: allowlist secret
    }  # pragma: allowlist secret
    assert _config(healed, "ocr_1") == {
        "base_url": "https://a.example",
        "api_key": "sk-a",  # pragma: allowlist secret
    }  # pragma: allowlist secret
    assert _config(healed, "ocr_2")["api_key"] == "sk-mistral"  # pragma: allowlist secret


def test_chain_reorder_across_kinds_never_cross_restores() -> None:
    stored = _chain_blob()
    incoming = redact_blob_secrets(stored)
    chain = incoming["nodes"][0]["nodes"]
    chain[0], chain[2] = chain[2], chain[0]
    chain[0]["id"], chain[2]["id"] = "ocr_0", "ocr_2"

    healed = restore_blob_secrets(incoming, stored)

    # mistral (no endpoint) landed on ocr_0: its stored key lives under ocr_2 of another kind → blanked
    assert _config(healed, "ocr_0")["api_key"] == ""
    # the openai_compatible step landed on ocr_2: a same-kind sibling at that endpoint is the source
    assert _config(healed, "ocr_2") == {
        "base_url": "https://a.example",
        "api_key": "sk-a",  # pragma: allowlist secret
    }  # pragma: allowlist secret


def test_endpoint_edit_in_place_is_refused_and_names_the_node_not_the_key() -> None:
    stored = _chain_blob()
    incoming = redact_blob_secrets(stored)
    _config(incoming, "ocr_1")["base_url"] = ATTACKER

    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, stored)

    assert caught.value.fields == [("ocr_1", "api_key")]
    assert isinstance(caught.value, ValueError)
    assert str(caught.value) == (
        "node 'ocr_1' api_key must be re-entered because its endpoint (base_url) differs from the one "
        "the secret belongs to — a stored or inherited secret is only used for the same provider at "
        'the same endpoint; send the secret explicitly (or "" to call it without one)'
    )
    assert "sk-b" not in str(caught.value)


def test_endpoint_edit_with_a_new_key_or_a_clear_is_accepted() -> None:
    stored = _chain_blob()
    for value in ("sk-new", ""):
        incoming = redact_blob_secrets(stored)
        _config(incoming, "gen_0")["base_url"] = ATTACKER
        _config(incoming, "gen_0")["api_key"] = value
        assert _config(restore_blob_secrets(incoming, stored), "gen_0")["api_key"] == value


def test_mask_without_a_same_provider_source_is_blanked_never_persisted() -> None:
    incoming = {"nodes": [_node("brand_new", "ocr", "mistral", api_key=MASK + "9f3a")]}
    healed = restore_blob_secrets(incoming, {"nodes": []})
    assert _config(healed, "brand_new")["api_key"] == ""
    assert restore_blob_secrets({"nodes": [_node("n", "ocr", "mistral")]}, None) == {
        "nodes": [_node("n", "ocr", "mistral")]
    }


def test_nested_target_endpoint_move_and_foreign_inheritor_are_refused() -> None:
    stored = _metagen_blob()

    moved = redact_blob_secrets(stored)
    _config(moved, "prep")["targets"][0]["base_url"] = "https://other.example/v1"
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(moved, stored)
    assert caught.value.fields == [("prep", "targets[summary].api_key")]

    inheritor = copy.deepcopy(stored)
    _config(inheritor, "prep")["targets"] = [
        {"field": "summary", "base_url": "https://third.example/v1"}
    ]
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(inheritor, stored)
    # reported by NestedSecrets.restore (moved key) AND NestedSecrets.foreign_inheritors: pinned as is
    assert caught.value.fields == [("prep", "targets[summary].api_key")] * 2

    keyless = copy.deepcopy(inheritor)
    _config(keyless, "prep")["targets"][0]["api_key"] = ""
    assert _config(restore_blob_secrets(keyless, stored), "prep")["targets"][0]["api_key"] == ""


def test_request_endpoint_step_at_a_foreign_endpoint_omitting_its_key_is_refused() -> None:
    def blob(step_config: dict) -> dict:
        return {
            "nodes": [
                _node(
                    "prep", "metagen", "document_prep", base_url=NODE_URL, api_key=KEY, model="m"
                ),
                {
                    "id": "loop",
                    "kind": "foreach",
                    "over": {"node_id": "prep"},
                    "body": {
                        "nodes": [_node("gen_0", "structgen", "openai_compatible", **step_config)]
                    },
                },
            ]
        }

    stored = blob({"base_url": NODE_URL, "api_key": KEY})
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(blob({"base_url": ATTACKER}), stored)
    # Today the step is reported twice: once by the identity heal (its stored key sits at another
    # endpoint) and once by RequestSecretGuard — pinned as is, a refactor must not change the list.
    assert caught.value.fields == [("gen_0", "api_key"), ("gen_0", "api_key")]
    assert (
        _config(restore_blob_secrets(blob({"base_url": ATTACKER, "api_key": ""}), stored), "gen_0")[
            "api_key"
        ]
        == ""
    )


def test_refusals_are_collected_in_node_order_across_the_whole_blob() -> None:
    stored = _chain_blob()
    incoming = redact_blob_secrets(stored)
    _config(incoming, "ocr_0")["base_url"] = ATTACKER
    _config(incoming, "gen_0")["base_url"] = ATTACKER

    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, stored)

    assert caught.value.fields == [("ocr_0", "api_key"), ("gen_0", "api_key")]


# ─────────────────────────── embed slots ───────────────────────────


def _embed(kind: str, config: dict) -> dict:
    return {"nodes": [{"id": "embed", "family": "embed", "kind": kind, "config": config}]}


def test_legacy_stored_embed_key_restores_the_migrated_slots_at_the_same_endpoint_only() -> None:
    stored = _embed("bge_server", {"base_url": "https://embed.example", "api_key": KEY})
    slot = {"kind": "bge_server", "base_url": "https://embed.example", "api_key": MASK}
    healed = restore_blob_secrets(_embed("dense_sparse", {"dense": slot, "sparse": None}), stored)
    assert healed["nodes"][0]["config"]["dense"]["api_key"] == KEY

    moved = dict(slot, base_url=ATTACKER)
    with pytest.raises(SecretReentryRequired):
        restore_blob_secrets(_embed("dense_sparse", {"dense": moved, "sparse": None}), stored)


def test_dense_sparse_slot_keys_are_masked_on_read() -> None:
    stored = _embed(
        "dense_sparse",
        {
            "dense": {"kind": "openai_compatible", "base_url": "https://e.example", "api_key": KEY},
            "sparse": {"kind": "bge_server", "base_url": "https://e.example", "api_key": KEY},
        },
    )
    config = redact_blob_secrets(stored)["nodes"][0]["config"]
    assert config["dense"]["api_key"] == config["sparse"]["api_key"] == MASK
