"""POST /collections/{id}/pipeline/stages/apply — the collection-scoped stage edit. The DB façade is
mocked at CONTEXT.database: a valid change persists through update_config (one config version) with the
stored secret kept, the response stage view is redacted, an invalid result / no-op persists nothing. The
write is a compare-and-swap on the config version read with the row: a lost race recomputes once on the
fresh head, a second loss is a 409 (never a silently overwritten concurrent write)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.pipelines.blob_secrets import MASK
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import SetStageConfig, StageCompiler
from shared_libs.services.db.facades import ConfigVersionConflictError

COLLECTION_ID = "4f1c2e3a-9070-4bd3-983c-27851179106b"
URL = f"/api/v1/collections/{COLLECTION_ID}/pipeline/stages/apply"


def _keyed_pipeline() -> dict:
    """The stock pipeline with a live api_key on the embed head's dense slot."""
    blob, _ = StageCompiler().apply(
        IngestPipeline.default_blob(),
        SetStageConfig(stage="embed", slot="dense", config={"api_key": "sk-live"}, mode="merge"),
    )
    return blob.model_dump(mode="json")


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    from backend.context import CONTEXT  # noqa: PLC0415 — deferred until app/ is on sys.path

    row = SimpleNamespace(
        id=uuid.UUID(COLLECTION_ID), pipeline=_keyed_pipeline(), search={}, needs_reindex=False
    )
    monkeypatch.setattr(
        CONTEXT.database.collections, "config_head", AsyncMock(return_value=(row, 7))
    )
    monkeypatch.setattr(
        CONTEXT.database.collections, "update_config", AsyncMock(return_value=False)
    )
    return CONTEXT


def _dense(stored: dict) -> dict:
    """The dense slot config of the stored embed node."""
    node = next(n for n in stored["nodes"] if n.get("family") == "embed")
    return node["config"]["dense"]


def _embed_view(body: dict) -> dict:
    return next(stage for stage in body["stages"] if stage["key"] == "embed")


def test_merge_persists_one_version_and_keeps_the_secret(client, wired) -> None:
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "mode": "merge",
        "config": {"timeout_seconds": 30.0},
    }
    response = client.post(URL, json={"action": action})
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True and body["valid"] is True
    update = wired.database.collections.update_config
    update.assert_awaited_once()
    stored = update.await_args.kwargs["pipeline"]
    head = _dense(stored)
    assert head["api_key"] == "sk-live"
    assert head["timeout_seconds"] == 30.0
    assert update.await_args.kwargs["note"] == "stage action: set_config 'embed'"
    assert update.await_args.kwargs["expected_version"] == 7
    # The returned view never carries the live key.
    assert "sk-live" not in response.text
    dense_view = next(slot for slot in _embed_view(body)["slots"] if slot["slot"] == "dense")
    assert dense_view["config"]["api_key"] == MASK


def test_replace_omitting_the_secret_keeps_it(client, wired) -> None:
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "config": {"base_url": "http://bge_server:80", "timeout_seconds": 45.0},
    }
    response = client.post(URL, json={"action": action})
    assert response.json()["persisted"] is True
    stored = wired.database.collections.update_config.await_args.kwargs["pipeline"]
    head = _dense(stored)
    assert head["api_key"] == "sk-live"


def test_noop_persists_nothing(client, wired) -> None:
    action = {"action": "enable_stage", "stage": "embed"}
    body = client.post(URL, json={"action": action}).json()
    assert body["persisted"] is False
    assert any("changed nothing" in notice for notice in body["notices"])
    wired.database.collections.update_config.assert_not_awaited()


def test_invalid_result_persists_nothing(client, wired) -> None:
    # The endpoint is restated: a replace that drops base_url moves the endpoint, which is a secret
    # re-entry 422 (see test_replace_onto_a_new_endpoint_never_carries_the_secret), not this case.
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "config": {"base_url": "http://bge_server:80", "bogus_key": 1},
    }
    body = client.post(URL, json={"action": action}).json()
    assert body["persisted"] is False and body["valid"] is False
    wired.database.collections.update_config.assert_not_awaited()


def test_build_error_never_echoes_a_secret(client, wired, capfd) -> None:
    # A missing required field on a keyed config: pydantic's str() embeds input_value={...whole
    # config...} carrying the key — neither the build_error nor the logs may.
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "mode": "merge",
        "config": {"base_url": None, "api_key": "sk-fresh-secret"},
    }
    response = client.post(URL, json={"action": action})
    body = response.json()
    assert body["valid"] is False and "base_url" in body["build_error"]
    assert "sk-fresh-secret" not in response.text and "sk-live" not in response.text
    logs = capfd.readouterr()
    assert "sk-fresh-secret" not in logs.out + logs.err
    assert "sk-live" not in logs.out + logs.err
    wired.database.collections.update_config.assert_not_awaited()


@pytest.mark.parametrize(
    "action",
    [
        {
            "action": "set_config",
            "stage": "embed",
            "slot": "dense",
            "config": {"base_url": "http://evil.example:9", "model": "x"},
        },
        {
            "action": "set_config",
            "stage": "embed",
            "slot": "dense",
            "mode": "merge",
            "config": {"base_url": "http://evil.example:9"},
        },
        {
            "action": "set_chain",
            "stage": "embed",
            "steps": [
                {
                    "kind": "dense_sparse",
                    "config": {
                        "dense": {"kind": "bge_server", "base_url": "http://evil.example:9"},
                        "sparse": None,
                    },
                }
            ],
        },
    ],
    ids=["replace", "merge", "set_chain"],
)
def test_a_new_endpoint_never_carries_the_secret(client, wired, action) -> None:
    response = client.post(URL, json={"action": action})
    assert response.status_code == 422
    assert "must be re-entered" in response.json()["detail"]
    assert "sk-live" not in response.text
    wired.database.collections.update_config.assert_not_awaited()


def test_a_new_endpoint_with_a_restated_key_persists(client, wired) -> None:
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "mode": "merge",
        "config": {"base_url": "http://other.example:9", "api_key": "sk-other"},
    }
    assert client.post(URL, json={"action": action}).json()["persisted"] is True
    stored = wired.database.collections.update_config.await_args.kwargs["pipeline"]
    head = _dense(stored)
    assert head["api_key"] == "sk-other"


def test_endpoint_spelling_variants_are_the_same_endpoint(client, wired) -> None:
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "mode": "merge",
        "config": {"base_url": "HTTP://BGE_SERVER:80/"},
    }
    assert client.post(URL, json={"action": action}).json()["persisted"] is True
    stored = wired.database.collections.update_config.await_args.kwargs["pipeline"]
    head = _dense(stored)
    assert head["api_key"] == "sk-live"


def test_merge_null_clears_the_secret(client, wired) -> None:
    action = {
        "action": "set_config",
        "stage": "embed",
        "slot": "dense",
        "mode": "merge",
        "config": {"api_key": None},
    }
    assert client.post(URL, json={"action": action}).json()["persisted"] is True
    stored = wired.database.collections.update_config.await_args.kwargs["pipeline"]
    head = _dense(stored)
    assert head["api_key"] == ""


def test_unknown_collection_is_404(client, fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT.database.collections, "config_head", AsyncMock(return_value=(None, 0))
    )
    response = client.post(URL, json={"action": {"action": "enable_stage", "stage": "embed"}})
    assert response.status_code == 404


_MERGE = {
    "action": "set_config",
    "stage": "embed",
    "slot": "dense",
    "mode": "merge",
    "config": {"timeout_seconds": 9.0},
}


def test_lost_race_recomputes_on_the_fresh_head(client, wired) -> None:
    """A concurrent write between read and write → re-read (new base) and CAS on the new version."""
    fresh = SimpleNamespace(
        id=uuid.UUID(COLLECTION_ID), pipeline=_keyed_pipeline(), search={}, needs_reindex=False
    )
    wired.database.collections.config_head.side_effect = [
        (wired.database.collections.config_head.return_value[0], 7),
        (fresh, 8),
    ]
    wired.database.collections.update_config.side_effect = [
        ConfigVersionConflictError(uuid.UUID(COLLECTION_ID), 7, 8),
        False,
    ]
    response = client.post(URL, json={"action": _MERGE})
    assert response.status_code == 200 and response.json()["persisted"] is True
    calls = wired.database.collections.update_config.await_args_list
    assert [call.kwargs["expected_version"] for call in calls] == [7, 8]


def test_repeated_lost_race_is_409_and_nothing_overwritten(client, wired) -> None:
    wired.database.collections.update_config.side_effect = ConfigVersionConflictError(
        uuid.UUID(COLLECTION_ID), 7, 8
    )
    response = client.post(URL, json={"action": _MERGE})
    assert response.status_code == 409
    assert wired.database.collections.update_config.await_count == 2
    assert "sk-live" not in response.text
