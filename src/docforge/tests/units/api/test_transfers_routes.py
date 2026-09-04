"""Collection transfer (export/import) endpoints — the API delivery over the async worker engine.

Covers the four routes' handler logic plus the two new queue-seam calls, all with the stores + queue
mocked (no compose stack): export opens a PENDING row + enqueues ids-only + is 404 on an unknown
collection + is cross-tenant 403; import stages the upload to a staging key + enqueues + needs CREATE
(it mints a brand-new collection, exactly like POST /collections);
the poll route shapes a row's status; download streams a done export and is 404 otherwise. The enqueue
seam is asserted to carry IDS/SCALARS ONLY — an arq control kwarg would crash the worker task.

All ``from backend...`` imports are deferred until the ``fastapi_app`` fixture has registered app/ on
sys.path (the autouse conftest fixture forces auth OFF; the scope tests pass explicit principals).
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


# ── shared fakes ──────────────────────────────────────────────────────────────────────────────


def _principal(*, permissions):
    """Build an AuthPrincipal directly (full access iff permissions is None)."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=permissions, revoked_at=None, user_id="user-1")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _scoped(collection_id: str):
    """A scoped key granting read+write on exactly one collection."""
    return _principal(
        permissions={"capabilities": ["read", "write"], "collections": [collection_id]}
    )


def _full():
    """A full-access (root / NULL-permission) principal."""
    return _principal(permissions=None)


def _transfer_row(**overrides):
    """A stand-in CollectionTransfer row carrying every field the status/download paths read."""
    from shared_libs.services.db.postgresql.tables import (  # noqa: PLC0415
        TransferKind,
        TransferStatus,
    )

    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    base = dict(
        id=uuid.uuid4(),
        kind=TransferKind.EXPORT,
        status=TransferStatus.DONE,
        collection_id=uuid.UUID(COLL_A),
        collection_name="Démo",
        s3_key="collection-exports/abc.dcexport",
        size_bytes=4096,
        format_version=1,
        dense_dim=1024,
        progress=100,
        stage="archive",
        counts={"documents": 19, "points": 42},
        error=None,
        expires_at=None,
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── POST /collections/{id}/export ───────────────────────────────────────────────────────────────


async def test_export_creates_row_and_enqueues_ids_only(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import export_collection  # noqa: PLC0415

    cid = uuid.UUID(COLL_A)
    row = _transfer_row(collection_id=cid, status="pending")
    collections = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=cid, name="Démo")))
    tracker = SimpleNamespace(create=AsyncMock(return_value=row))
    enqueue = AsyncMock()
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, transfer_tracker=tracker)
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_export", enqueue)

    result = await export_collection(collection_id=cid, principal=_full())

    # 202 shape: the pollable transfer id + kind + status.
    assert result.transfer_id == str(row.id)
    assert result.kind == "export"
    # The row is created PENDING BEFORE the enqueue.
    tracker.create.assert_awaited_once()
    # IDS ONLY on the wire — no arq control kwarg (it would crash export_collection).
    enqueue.assert_awaited_once_with(str(cid), str(row.id))
    _, kwargs = enqueue.await_args
    assert kwargs == {}


async def test_export_unknown_collection_is_404_and_enqueues_nothing(
    fastapi_app, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import export_collection  # noqa: PLC0415

    collections = SimpleNamespace(get=AsyncMock(return_value=None))
    tracker = SimpleNamespace(create=AsyncMock())
    enqueue = AsyncMock()
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, transfer_tracker=tracker)
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_export", enqueue)

    with pytest.raises(HTTPException) as exc:
        await export_collection(collection_id=uuid.uuid4(), principal=_full())

    assert exc.value.status_code == 404
    # Fail-fast: no row created, nothing enqueued.
    tracker.create.assert_not_awaited()
    enqueue.assert_not_awaited()


async def test_export_scoped_key_foreign_is_403(fastapi_app) -> None:
    """The READ gate path-scopes collection_id; a key scoped to A cannot export B."""
    from fastapi import Request  # noqa: PLC0415

    from backend.libs.auth import AuthzGuard, Capability  # noqa: PLC0415

    # The `require` gate reads the collection_id PATH param — simulate it directly.
    scope = Request({"type": "http", "path_params": {"collection_id": COLL_B}, "headers": []})
    with pytest.raises(HTTPException) as exc:
        AuthzGuard.enforce(Capability.READ, _scoped(COLL_A), scope)

    assert exc.value.status_code == 403


# ── POST /collections/import ────────────────────────────────────────────────────────────────────


async def test_import_is_gated_on_create_capability_not_write(fastapi_app) -> None:
    """Import mints a brand-new collection, so it is gated on CREATE (like POST /collections), not

    WRITE — a WRITE-only scoped key can no longer escalate to collection creation by importing a
    bundle. Exercises the exact gate the route declares: ``require(Capability.CREATE)``.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    from backend.libs.auth import Capability, require  # noqa: PLC0415

    def _req(principal):
        return SimpleNamespace(headers={}, path_params={}, state=SimpleNamespace(principal=principal))

    gate = require(Capability.CREATE)

    # A read+write scoped key (no create) is rejected — the escalation the fix closes.
    with pytest.raises(HTTPException) as exc:
        await gate(_req(_scoped(COLL_A)))
    assert exc.value.status_code == 403

    # A CREATE-capable key passes the gate.
    creator = _principal(permissions={"capabilities": ["create"], "collections": ["*"]})
    assert await gate(_req(creator)) is creator


async def test_import_stages_upload_and_enqueues(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.helpers import TransferHelpers  # noqa: PLC0415
    from backend.routers.transfers.router import import_collection  # noqa: PLC0415

    row = _transfer_row(kind="import", collection_id=None, status="pending", s3_key=None)
    tracker = SimpleNamespace(create=AsyncMock(return_value=row))
    transfer = SimpleNamespace(stage_bundle=AsyncMock(return_value=1234))
    enqueue = AsyncMock()
    stage_upload = AsyncMock(return_value=1234)
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(transfer_tracker=tracker, transfer=transfer)
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_import", enqueue)
    # Spy on the upload helper so we assert a staging key was staged before the row/enqueue.
    monkeypatch.setattr(TransferHelpers, "stage_upload", stage_upload)

    upload = SimpleNamespace(read=AsyncMock(side_effect=[b"data", b""]), filename="b.dcexport")
    result = await import_collection(file=upload, target_name="Imported Copy", principal=_full())

    assert result.kind == "import"
    assert result.transfer_id == str(row.id)
    # Staged to S3 BEFORE the tracking row is created.
    stage_upload.assert_awaited_once()
    staged_key = stage_upload.await_args.args[1]
    assert staged_key.startswith("collection-imports/")
    tracker.create.assert_awaited_once()
    # Enqueue carries the staged key + row id + the normalized target name — scalars only.
    enqueue.assert_awaited_once_with(staged_key, str(row.id), "Imported Copy")
    _, kwargs = enqueue.await_args
    assert kwargs == {}


async def test_import_blank_target_name_normalizes_to_none(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.helpers import TransferHelpers  # noqa: PLC0415
    from backend.routers.transfers.router import import_collection  # noqa: PLC0415

    row = _transfer_row(kind="import", collection_id=None, status="pending", s3_key=None)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            transfer_tracker=SimpleNamespace(create=AsyncMock(return_value=row)),
            transfer=SimpleNamespace(),
        ),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.queue, "enqueue_import", enqueue)
    monkeypatch.setattr(TransferHelpers, "stage_upload", AsyncMock(return_value=1))

    upload = SimpleNamespace(read=AsyncMock(side_effect=[b""]), filename="b.dcexport")
    await import_collection(file=upload, target_name="   ", principal=_full())

    # A blank multipart field means "no target name" → None on the wire.
    assert enqueue.await_args.args[2] is None


def test_import_requires_write_capability(fastapi_app) -> None:
    """A SEARCH/READ-only key cannot import (create) a collection — WRITE is demanded."""
    from fastapi import Request  # noqa: PLC0415

    from backend.libs.auth import AuthzGuard, Capability  # noqa: PLC0415

    read_only = _principal(permissions={"capabilities": ["read"], "collections": ["*"]})
    scope = Request({"type": "http", "path_params": {}, "headers": []})
    with pytest.raises(HTTPException) as exc:
        AuthzGuard.enforce(Capability.WRITE, read_only, scope)

    assert exc.value.status_code == 403


# ── GET /transfers/{id} ─────────────────────────────────────────────────────────────────────────


async def test_get_transfer_shapes_status(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import get_transfer  # noqa: PLC0415

    row = _transfer_row()
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=row))),
    )

    result = await get_transfer(transfer_id=row.id, principal=_full())

    assert result.status == "done"
    assert result.kind == "export"
    assert result.progress == 100
    assert result.counts == {"documents": 19, "points": 42}
    assert result.size_bytes == 4096
    assert result.collection_id == COLL_A


async def test_get_transfer_unknown_is_404(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import get_transfer  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=None))),
    )

    with pytest.raises(HTTPException) as exc:
        await get_transfer(transfer_id=uuid.uuid4(), principal=_full())

    assert exc.value.status_code == 404


async def test_get_transfer_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import get_transfer  # noqa: PLC0415

    row = _transfer_row(collection_id=uuid.UUID(COLL_B))
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=row))),
    )

    with pytest.raises(HTTPException) as exc:
        await get_transfer(transfer_id=row.id, principal=_scoped(COLL_A))

    assert exc.value.status_code == 403


# ── GET /transfers/{id}/download ────────────────────────────────────────────────────────────────


async def test_download_streams_a_done_export(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import download_transfer  # noqa: PLC0415

    row = _transfer_row()

    async def _fake_stream(_key):
        yield b"bundle-bytes"

    transfer = SimpleNamespace(stream_bundle=lambda key: _fake_stream(key))
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=row)), transfer=transfer
        ),
    )

    response = await download_transfer(transfer_id=row.id, principal=_full())

    assert response.media_type == "application/zstd"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert ".dcexport" in disposition
    # The body streams the S3 bytes.
    chunks = [chunk async for chunk in response.body_iterator]
    assert b"".join(chunks) == b"bundle-bytes"


async def test_download_import_row_is_404(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import download_transfer  # noqa: PLC0415

    row = _transfer_row(kind="import", collection_id=None)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=row))),
    )

    with pytest.raises(HTTPException) as exc:
        await download_transfer(transfer_id=row.id, principal=_full())

    assert exc.value.status_code == 404


async def test_download_unfinished_export_is_404(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import download_transfer  # noqa: PLC0415

    row = _transfer_row(status="running", s3_key=None)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=row))),
    )

    with pytest.raises(HTTPException) as exc:
        await download_transfer(transfer_id=row.id, principal=_full())

    assert exc.value.status_code == 404


async def test_download_expired_bundle_is_404(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.transfers.router import download_transfer  # noqa: PLC0415

    row = _transfer_row(expires_at=datetime.now(UTC) - timedelta(hours=1))
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(transfer_tracker=SimpleNamespace(get=AsyncMock(return_value=row))),
    )

    with pytest.raises(HTTPException) as exc:
        await download_transfer(transfer_id=row.id, principal=_full())

    assert exc.value.status_code == 404


# ── import upload size cap (stage_upload) ───────────────────────────────────────────────────────


async def test_stage_upload_rejects_oversized_bundle(fastapi_app) -> None:
    """The spool aborts with a 413 past the ceiling and stages NOTHING (no partial S3 object)."""
    from backend.routers.transfers.helpers import TransferHelpers  # noqa: PLC0415

    # Three 4-byte windows = 12 bytes streamed; the 8-byte ceiling trips on the second window.
    file = SimpleNamespace(read=AsyncMock(side_effect=[b"aaaa", b"bbbb", b"cccc", b""]))
    stage_bundle = AsyncMock()
    transfer = SimpleNamespace(stage_bundle=stage_bundle)

    with pytest.raises(HTTPException) as exc:
        await TransferHelpers.stage_upload(file, "collection-imports/x.dcexport", transfer, 8)

    assert exc.value.status_code == 413
    # The S3 PUT never ran — an aborted upload leaves no staged object.
    stage_bundle.assert_not_awaited()


async def test_stage_upload_accepts_within_limit(fastapi_app) -> None:
    from backend.routers.transfers.helpers import TransferHelpers  # noqa: PLC0415

    file = SimpleNamespace(read=AsyncMock(side_effect=[b"aaaa", b""]))
    stage_bundle = AsyncMock(return_value=4)
    transfer = SimpleNamespace(stage_bundle=stage_bundle)

    size = await TransferHelpers.stage_upload(file, "collection-imports/x.dcexport", transfer, 1000)

    assert size == 4
    stage_bundle.assert_awaited_once()


# ── the queue seam (ids/scalars only) ───────────────────────────────────────────────────────────


def _queue_with_fake_pool(fastapi_app):
    """A QueueClient whose lazy pool is pre-seeded with an AsyncMock (no Redis touched)."""
    from backend.utils.queue import QueueClient  # noqa: PLC0415

    client = QueueClient("redis://localhost:6379")
    pool = AsyncMock()
    client._pool = pool
    return client, pool


async def test_enqueue_export_is_ids_only(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_export("coll-1", "transfer-1")

    pool.enqueue_job.assert_awaited_once_with("export_collection", "coll-1", "transfer-1")
    _, kwargs = pool.enqueue_job.await_args
    assert kwargs == {}, "enqueue_export must pass no control kwargs (arq rejects _job_timeout)"


async def test_enqueue_import_is_scalars_only(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_import("collection-imports/x.dcexport", "transfer-1", "Copy")

    pool.enqueue_job.assert_awaited_once_with(
        "import_collection", "collection-imports/x.dcexport", "transfer-1", "Copy"
    )
    _, kwargs = pool.enqueue_job.await_args
    assert kwargs == {}


async def test_enqueue_import_carries_none_target_name(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_import("collection-imports/x.dcexport", "transfer-1", None)

    pool.enqueue_job.assert_awaited_once_with(
        "import_collection", "collection-imports/x.dcexport", "transfer-1", None
    )
