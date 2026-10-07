"""Cross-node secret fallbacks: the endpoint rule for NESTED overrides and NESTED secrets.

Pins the security fixes behind the release block:
  HIGH-1 — a metagen per-field target with its own base_url never inherits the node's key (runtime),
           and a write relying on that inheritance is refused (SecretReentryRequired).
  HIGH-2 — a structgen step override at a foreign endpoint is refused on write (runtime: test_structgen).
  HIGH-3 — ``targets[*].api_key`` is masked on every outbound surface, restored by (field, endpoint),
           and never cross-restored onto a target whose endpoint changed.
  LOW-1  — an unparseable port never normalises to the scheme's default port.
"""

import copy
import uuid

import pytest

from shared_libs.pipelines.blob_secrets import (
    MASK,
    SecretReentryRequired,
    has_blob_secrets,
    redact_blob_secrets,
    redact_config_snapshot,
    restore_blob_secrets,
)
from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.nodes.metagen.prep.document import (
    MetagenDocumentPrepConfig,
    MetagenDocumentPrepNode,
)
from shared_libs.pipelines.ingest.stages import EnableStage, SetStageConfig, StageCompiler
from shared_libs.pipelines.ingest.stages.config_merge import StageConfigMerge
from shared_libs.pipelines.secret_identity import SecretIdentity
from shared_libs.public_models import (
    CollectionContract,
    FieldOrigin,
    FieldScope,
    FieldType,
    MetadataFieldSpec,
)

NODE_URL = "https://llm.example/v1"
ATTACKER = "https://attacker.example/v1"
NODE_KEY = "sk-NODESECRET-1111"
TARGET_KEY = "sk-TARGETSECRET-2222"

CONTRACT = CollectionContract(
    collection_id=uuid.uuid4(),
    name="c",
    supported_formats=["pdf"],
    max_file_size_bytes=1,
    fields=[
        MetadataFieldSpec(
            field_name=name,
            field_type=FieldType.STRING,
            origin=FieldOrigin.GENERATED,
            scope=FieldScope.DOCUMENT,
        )
        for name in ("summary", "topic")
    ],
)


def _endpoint_for(targets: list[dict]) -> dict[str, str]:
    """Resolve a document prep's targets and return field → the api_key its call would send."""
    config = MetagenDocumentPrepConfig(
        base_url=NODE_URL, api_key=NODE_KEY, model="m", targets=targets
    )
    node = MetagenDocumentPrepNode(id="p", config=config)
    resolved = node._resolve_targets(CONTRACT, FieldScope.DOCUMENT)
    return {target.spec.field_name: target.endpoint.api_key for target in resolved}


# ─────────────────────────── HIGH-1 runtime ───────────────────────────


def test_target_at_foreign_endpoint_never_receives_the_node_key() -> None:
    keys = _endpoint_for([{"field": "summary", "base_url": ATTACKER}])
    assert keys["summary"] == ""


def test_target_without_or_at_same_endpoint_inherits_the_node_key() -> None:
    keys = _endpoint_for(
        [{"field": "summary"}, {"field": "topic", "base_url": "HTTPS://LLM.example:443/v1/"}]
    )
    assert keys == {"summary": NODE_KEY, "topic": NODE_KEY}


def test_endpointless_override_key_is_ignored_for_the_parent_key() -> None:
    """An override key without its own base_url is bound to nothing: the call goes to the parent's
    endpoint with the parent's key, so a caller who moves the parent can never pull that key along."""
    assert SecretIdentity.scoped_secret("", "sk-OWN", ATTACKER, "") == ""
    assert (
        SecretIdentity.scoped_secret("", "sk-OWN", "https://llm.example/v1", NODE_KEY) == NODE_KEY
    )


def test_target_with_its_own_key_sends_its_own_key() -> None:
    keys = _endpoint_for([{"field": "summary", "base_url": ATTACKER, "api_key": TARGET_KEY}])
    assert keys["summary"] == TARGET_KEY


# ─────────────────────────── write side (HIGH-1 / HIGH-2) ───────────────────────────


def _metagen_blob(prep_config: dict | None = None, step_config: dict | None = None) -> dict:
    """The stock blob with document metagen on; the prep keyed at NODE_URL unless overridden."""
    blob, _ = StageCompiler().apply(
        IngestPipeline.default_blob(), EnableStage(stage="metagen_document")
    )
    dumped = blob.model_dump(mode="json")
    for node in dumped["nodes"]:
        if node.get("kind") == "document_prep":
            node["config"] = prep_config or {
                "base_url": NODE_URL,
                "api_key": NODE_KEY,
                "model": "m",
            }
        body = node.get("body")
        if isinstance(body, dict) and step_config is not None:
            for step in body["nodes"]:
                if step.get("family") == "structgen":
                    step["config"] = step_config
    return dumped


def _prep(blob: dict) -> dict:
    return next(n for n in blob["nodes"] if n.get("kind") == "document_prep")["config"]


def test_write_target_at_foreign_endpoint_omitting_its_key_is_refused() -> None:
    stored = _metagen_blob()
    incoming = copy.deepcopy(stored)
    _prep(incoming)["targets"] = [{"field": "summary", "base_url": ATTACKER}]
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, stored)
    assert caught.value.fields == [("meta_doc_prep", "targets[summary].api_key")]
    assert NODE_KEY not in str(caught.value)


def test_write_target_at_foreign_endpoint_with_explicit_empty_key_is_accepted() -> None:
    stored = _metagen_blob()
    incoming = copy.deepcopy(stored)
    _prep(incoming)["targets"] = [{"field": "summary", "base_url": ATTACKER, "api_key": ""}]
    healed = restore_blob_secrets(incoming, stored)
    assert _prep(healed)["targets"][0]["api_key"] == ""


def test_write_target_at_same_endpoint_omitting_its_key_is_accepted() -> None:
    stored = _metagen_blob()
    incoming = copy.deepcopy(stored)
    _prep(incoming)["targets"] = [{"field": "summary", "base_url": NODE_URL + "/"}]
    assert "api_key" not in _prep(restore_blob_secrets(incoming, stored))["targets"][0]


def test_write_structgen_step_at_foreign_endpoint_omitting_its_key_is_refused() -> None:
    stored = _metagen_blob()
    incoming = _metagen_blob(step_config={"base_url": ATTACKER})
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, stored)
    assert caught.value.fields == [("gen_0", "api_key")]


def test_write_structgen_step_with_explicit_key_or_same_endpoint_is_accepted() -> None:
    stored = _metagen_blob()
    restore_blob_secrets(_metagen_blob(step_config={"base_url": ATTACKER, "api_key": ""}), stored)
    restore_blob_secrets(_metagen_blob(step_config={"base_url": NODE_URL}), stored)


def test_stage_merge_of_attacker_target_is_refused_end_to_end() -> None:
    """The live repro: set_config merge of targets → compile → write path refuses it."""
    stored = _metagen_blob()
    compiled, _ = StageCompiler().apply(
        GroupNodeBlob.model_validate(stored),
        SetStageConfig(
            stage="metagen_document",
            config={"targets": [{"field": "summary", "base_url": ATTACKER}]},
            mode="merge",
        ),
    )
    with pytest.raises(SecretReentryRequired):
        restore_blob_secrets(compiled.model_dump(mode="json"), stored)


# ─────────────────────────── HIGH-3 nested masking + restore ───────────────────────────


def _keyed_targets_blob(target_url: str = ATTACKER) -> dict:
    return _metagen_blob(
        prep_config={
            "base_url": NODE_URL,
            "api_key": NODE_KEY,
            "model": "m",
            "targets": [
                {"field": "summary", "base_url": target_url, "api_key": TARGET_KEY},
                {"field": "topic"},
            ],
        }
    )


def test_redact_masks_nested_target_keys_without_mutating_the_store() -> None:
    stored = _keyed_targets_blob()
    masked = redact_blob_secrets(stored)
    assert TARGET_KEY not in str(masked) and NODE_KEY not in str(masked)
    assert _prep(masked)["targets"][0]["api_key"] == MASK
    assert _prep(stored)["targets"][0]["api_key"] == TARGET_KEY
    snapshot = redact_config_snapshot({"pipeline": stored, "search": {}})
    assert TARGET_KEY not in str(snapshot)


def test_has_blob_secrets_sees_a_nested_key() -> None:
    blob = {"nodes": [{"id": "p", "config": {"targets": [{"field": "s", "api_key": TARGET_KEY}]}}]}
    assert has_blob_secrets(blob)
    assert not has_blob_secrets({"nodes": [{"id": "p", "config": {"targets": [{"field": "s"}]}}]})


def test_masked_nested_key_is_restored_by_field_even_after_a_reorder() -> None:
    stored = _keyed_targets_blob()
    incoming = redact_blob_secrets(stored)
    _prep(incoming)["targets"].reverse()
    healed = _prep(restore_blob_secrets(incoming, stored))
    by_field = {t["field"]: t for t in healed["targets"]}
    assert by_field["summary"]["api_key"] == TARGET_KEY
    assert healed["api_key"] == NODE_KEY


def test_masked_nested_key_is_never_cross_restored_onto_a_moved_target() -> None:
    stored = _keyed_targets_blob()
    incoming = redact_blob_secrets(stored)
    _prep(incoming)["targets"][0]["base_url"] = "https://other.example/v1"
    with pytest.raises(SecretReentryRequired) as caught:
        restore_blob_secrets(incoming, stored)
    assert ("meta_doc_prep", "targets[summary].api_key") in caught.value.fields
    assert TARGET_KEY not in str(caught.value)


def test_merge_moving_the_node_endpoint_drops_inheriting_target_keys() -> None:
    current = {
        "base_url": NODE_URL,
        "api_key": NODE_KEY,
        "targets": [{"field": "summary", "api_key": TARGET_KEY}],
    }
    merged = StageConfigMerge.resolve(current, {"base_url": ATTACKER}, "merge")
    assert "api_key" not in merged["targets"][0]
    assert current["targets"][0]["api_key"] == TARGET_KEY  # current never mutated


# ─────────────────────────── HTTP surfaces ───────────────────────────


def test_collection_get_and_list_mask_nested_keys(client, monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from test_collections_secret_redaction import _fake_collection, _mock_db  # noqa: PLC0415

    fake = _fake_collection(_keyed_targets_blob(), {})
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        list_all=AsyncMock(return_value=[fake]),
        get_schema=AsyncMock(return_value=[]),
    )
    for url in (f"/api/v1/collections/{fake.id}", "/api/v1/collections"):
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert TARGET_KEY not in response.text and NODE_KEY not in response.text


def test_snippet_export_masks_nested_keys(client, fastapi_app, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from backend.context import CONTEXT  # noqa: PLC0415

    row = SimpleNamespace(id=uuid.uuid4(), pipeline=_keyed_targets_blob(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(CONTEXT.database.index_state, "missing", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT.database.collection_aliases, "name_is_alias", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        CONTEXT.database.collection_aliases, "names_for", AsyncMock(return_value=[])
    )
    response = client.get(f"/api/v1/collections/{row.id}/snippets/pipeline")
    assert response.status_code == 200, response.text
    assert TARGET_KEY not in response.text and NODE_KEY not in response.text


# ─────────────────────────── LOW-1 ───────────────────────────


def test_invalid_port_never_collapses_to_the_default_port() -> None:
    assert SecretIdentity.normalize("https://h:bogus/v1") == "https://h:bogus/v1"
    assert SecretIdentity.normalize("https://h:bogus") != SecretIdentity.normalize("https://h")
    assert not SecretIdentity.same_endpoint("https://h:99999", "https://h")
