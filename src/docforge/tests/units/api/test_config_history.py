"""Versioned config history (G3): author stamped at every write site, the list / masked get / diff
routes, and the restore secret rule (current same-endpoint key wins, a moved endpoint is a 422, a
provider without a current key gets the snapshot's own key back). CONTEXT.database is mocked."""

import copy
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.pipelines.blob_secrets import MASK
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import SetStageConfig, StageCompiler
from shared_libs.services.db.facades import (
    ConfigVersionConflictError,
    ConfigVersionPage,
)

CID = "4f1c2e3a-9070-4bd3-983c-27851179106b"
BASE = f"/api/v1/collections/{CID}/config-versions"


def _pipeline(**embed: object) -> dict:
    """The stock pipeline with the embed head config merged."""
    blob, _ = StageCompiler().apply(
        IngestPipeline.default_blob(), SetStageConfig(stage="embed", config=embed, mode="merge")
    )
    return blob.model_dump(mode="json")


def _embed(blob: dict) -> dict:
    return next(n for n in blob["nodes"] if n.get("kind") == "bge_server")["config"]


def _version(n: int, pipeline: dict, search: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        version=n,
        created_at=datetime(2026, 10, 7, tzinfo=UTC),
        note=f"v{n}",
        author_label="ops-key",
        author_key_id=None,
        config={"pipeline": pipeline, "search": search or {}},
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    from backend.context import CONTEXT  # noqa: PLC0415 — deferred until app/ is on sys.path

    v1 = _version(1, _pipeline(api_key="sk-old", timeout_seconds=10.0))
    v2 = _version(2, _pipeline(api_key="sk-new", timeout_seconds=20.0))
    rows = {1: v1, 2: v2}
    current = SimpleNamespace(
        id=uuid.UUID(CID),
        pipeline=copy.deepcopy(v2.config["pipeline"]),
        search={},
        needs_reindex=False,
    )
    history = SimpleNamespace(
        get=AsyncMock(side_effect=lambda _cid, n: rows.get(n)),
        list_page=AsyncMock(
            return_value=ConfigVersionPage(items=[v2, v1], predecessor=None, total=2)
        ),
    )
    monkeypatch.setattr(CONTEXT.database, "config_history", history)
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=current))
    monkeypatch.setattr(
        CONTEXT.database.collections, "config_head", AsyncMock(return_value=(current, 2))
    )
    monkeypatch.setattr(
        CONTEXT.database.collections, "update_config", AsyncMock(return_value=False)
    )
    return SimpleNamespace(ctx=CONTEXT, rows=rows, current=current)


# ------------------------------- reads -------------------------------


def test_list_summarises_each_version_against_its_predecessor(client, wired) -> None:
    body = client.get(BASE).json()
    assert body["total"] == 2 and [i["version"] for i in body["items"]] == [2, 1]
    assert body["items"][0]["changes"] == ["pipeline:embed"]
    assert body["items"][1]["changes"] == []  # version 1 has no predecessor
    assert body["items"][0]["author_label"] == "ops-key"


def test_get_masks_every_secret(client, wired) -> None:
    response = client.get(f"{BASE}/2")
    assert response.status_code == 200
    assert "sk-new" not in response.text
    assert _embed(response.json()["config"]["pipeline"])["api_key"] == MASK


def test_get_unknown_version_is_404(client, wired) -> None:
    assert client.get(f"{BASE}/9").status_code == 404


def test_diff_reports_changed_paths_with_masked_values(client, wired) -> None:
    response = client.get(f"{BASE}/diff", params={"from": 1, "to": 2})
    assert response.status_code == 200
    assert "sk-old" not in response.text and "sk-new" not in response.text
    changes = {c["path"]: c for c in response.json()["changes"]}
    timeout = changes["/pipeline/nodes/embed/config/timeout_seconds"]
    assert (timeout["op"], timeout["before"], timeout["after"]) == ("changed", 10.0, 20.0)
    key = changes["/pipeline/nodes/embed/config/api_key"]  # a rotation shows, both sides masked
    assert key["before"] == MASK and key["after"] == MASK


# ------------------------------- restore -------------------------------


def test_restore_writes_a_new_version_keeping_the_current_same_endpoint_key(client, wired) -> None:
    response = client.post(f"{BASE}/1/restore")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "collection_id": CID,
        "restored_from": 1,
        "version": 3,
        "needs_reindex": False,
    }
    kwargs = wired.ctx.database.collections.update_config.await_args.kwargs
    assert kwargs["note"] == "restore of v1" and kwargs["expected_version"] == 2
    assert kwargs["author"].label == "anonymous"
    stored = _embed(kwargs["pipeline"])
    assert stored["timeout_seconds"] == 10.0  # v1's config …
    assert stored["api_key"] == "sk-new"  # … but the rotated CURRENT key, never v1's old one


def test_restore_refuses_a_moved_endpoint_with_422(client, wired) -> None:
    wired.current.pipeline = _pipeline(api_key="sk-elsewhere", base_url="http://other:80")
    response = client.post(f"{BASE}/1/restore")
    assert response.status_code == 422
    assert "re-entered" in response.json()["detail"]
    wired.ctx.database.collections.update_config.assert_not_awaited()


def test_restore_uses_the_snapshot_key_when_the_current_has_none(client, wired) -> None:
    wired.current.pipeline = _pipeline(api_key="")
    assert client.post(f"{BASE}/1/restore").status_code == 200
    kwargs = wired.ctx.database.collections.update_config.await_args.kwargs
    assert _embed(kwargs["pipeline"])["api_key"] == "sk-old"


def test_restore_lost_race_is_409(client, wired) -> None:
    wired.ctx.database.collections.update_config.side_effect = ConfigVersionConflictError(
        uuid.UUID(CID), 2, 3
    )
    assert client.post(f"{BASE}/1/restore").status_code == 409


# ------------------------------- author at write sites -------------------------------


def test_stage_apply_records_the_author(client, wired) -> None:
    action = {
        "action": "set_config",
        "stage": "embed",
        "mode": "merge",
        "config": {"timeout_seconds": 33.0},
    }
    response = client.post(
        f"/api/v1/collections/{CID}/pipeline/stages/apply", json={"action": action}
    )
    assert response.status_code == 200
    author = wired.ctx.database.collections.update_config.await_args.kwargs["author"]
    assert author.label == "anonymous" and author.key_id is None


def test_snippet_apply_records_the_author(client, wired, monkeypatch) -> None:
    monkeypatch.setattr(wired.ctx.database.collections, "get_schema", AsyncMock(return_value=[]))
    snippet = client.get(f"/api/v1/collections/{CID}/snippets/search").json()
    assert (
        client.post(f"/api/v1/collections/{CID}/snippets/search", json=snippet).status_code == 200
    )
    author = wired.ctx.database.collections.update_config.await_args.kwargs["author"]
    assert author.label == "anonymous"


def test_patch_records_the_author(client, wired, monkeypatch) -> None:
    from shared_libs.services.db.facades import CollectionUpdateResult  # noqa: PLC0415

    apply_update = AsyncMock(
        return_value=CollectionUpdateResult(schema_applied=False, schema_reindex_required=False)
    )
    monkeypatch.setattr(wired.ctx.database.collections, "apply_update", apply_update)
    # The response rebuild is out of scope here: stop right after the write.
    monkeypatch.setattr(
        wired.ctx.database.collections, "get_schema", AsyncMock(side_effect=StopAsyncIteration)
    )
    client.patch(f"/api/v1/collections/{CID}", json={"search": {}})
    assert apply_update.await_args.args[1].author.label == "anonymous"


def test_author_resolver_names_the_key_the_user_or_anonymous(fastapi_app) -> None:
    from backend.libs.config_history import ConfigAuthorResolver  # noqa: PLC0415

    key_id = uuid.uuid4()
    keyed = SimpleNamespace(
        key=SimpleNamespace(id=key_id, name="ci-bot", prefix="df_ab12"), user=None
    )
    assert ConfigAuthorResolver.from_principal(keyed).key_id == key_id
    assert ConfigAuthorResolver.from_principal(keyed).label == "ci-bot (df_ab12)"
    user_only = SimpleNamespace(key=None, user=SimpleNamespace(username="alice"))
    assert ConfigAuthorResolver.from_principal(user_only).label == "alice"
    anonymous = SimpleNamespace(key=None, user=None)
    assert ConfigAuthorResolver.from_principal(anonymous).label == "anonymous"
