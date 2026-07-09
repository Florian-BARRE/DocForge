"""P5 enablement routes: the PATCH toggle surface wired to the enablement facade (mocked). A
document toggle is a single PG flag; chunk toggles echo the recomputed effective state and the
reindex flag; unknown ids are a 404 (single) or listed in ``not_found`` (bulk). No live stack."""

import uuid
from unittest.mock import AsyncMock

from shared_libs.services.db.facades import ChunkToggle

DOC_ID = "44444444-4444-4444-4444-444444444444"


def test_toggle_routes_are_registered(fastapi_app) -> None:
    """The three PATCH toggle routes are part of the API contract."""
    paths = fastapi_app.openapi()["paths"]
    assert "patch" in paths["/api/v1/documents/{document_id}/enabled"]
    assert "patch" in paths["/api/v1/chunks/{chunk_id}/enabled"]
    assert "patch" in paths["/api/v1/chunks/enabled"]


def test_document_toggle_flips_and_echoes(client, monkeypatch) -> None:
    """PATCH a document → the facade flips documents.enabled and the applied state is echoed."""
    from backend.context import CONTEXT

    set_enabled = AsyncMock(return_value=True)
    monkeypatch.setattr(CONTEXT.database.enablement, "set_document_enabled", set_enabled)

    response = client.patch(f"/api/v1/documents/{DOC_ID}/enabled", json={"enabled": False})

    assert response.status_code == 200, response.text
    assert response.json() == {"document_id": DOC_ID, "enabled": False}
    assert set_enabled.await_args.args[1] is False


def test_document_toggle_unknown_is_404(client, monkeypatch) -> None:
    """An unknown document id is an explicit 404."""
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.enablement, "set_document_enabled", AsyncMock(return_value=False)
    )
    response = client.patch(f"/api/v1/documents/{DOC_ID}/enabled", json={"enabled": True})
    assert response.status_code == 404, response.text


def test_chunk_toggle_echoes_effective_and_reindex(client, monkeypatch) -> None:
    """PATCH a chunk → the recomputed effective state + reindex flag from the facade outcome."""
    from backend.context import CONTEXT

    chunk_id = uuid.uuid4()
    toggle = AsyncMock(return_value=[ChunkToggle(chunk_id=chunk_id, enabled=True, reindex_required=False)])
    monkeypatch.setattr(CONTEXT.database.enablement, "set_chunks_enabled", toggle)

    response = client.patch(f"/api/v1/chunks/{chunk_id}/enabled", json={"enabled": True})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "chunk_id": str(chunk_id),
        "enabled": True,
        "reindex_required": False,
    }
    # The single route delegates as a one-element bulk call.
    assert toggle.await_args.args[0] == [chunk_id]


def test_chunk_toggle_never_embedded_reports_reindex(client, monkeypatch) -> None:
    """Enabling a never-embedded chunk surfaces reindex_required=True (no false 'searchable')."""
    from backend.context import CONTEXT

    chunk_id = uuid.uuid4()
    toggle = AsyncMock(return_value=[ChunkToggle(chunk_id=chunk_id, enabled=True, reindex_required=True)])
    monkeypatch.setattr(CONTEXT.database.enablement, "set_chunks_enabled", toggle)

    response = client.patch(f"/api/v1/chunks/{chunk_id}/enabled", json={"enabled": True})

    assert response.status_code == 200, response.text
    assert response.json()["reindex_required"] is True


def test_chunk_toggle_unknown_is_404(client, monkeypatch) -> None:
    """A chunk id that resolves to nothing is a 404 on the single route."""
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.enablement, "set_chunks_enabled", AsyncMock(return_value=[])
    )
    response = client.patch(f"/api/v1/chunks/{uuid.uuid4()}/enabled", json={"enabled": False})
    assert response.status_code == 404, response.text


def test_bulk_chunk_toggle_reports_results_and_not_found(client, monkeypatch) -> None:
    """Bulk toggle → per-chunk outcomes, and the requested ids with no chunk go to not_found."""
    from backend.context import CONTEXT

    known = uuid.uuid4()
    missing = uuid.uuid4()
    toggle = AsyncMock(return_value=[ChunkToggle(chunk_id=known, enabled=False, reindex_required=False)])
    monkeypatch.setattr(CONTEXT.database.enablement, "set_chunks_enabled", toggle)

    response = client.patch(
        "/api/v1/chunks/enabled",
        json={"chunk_ids": [str(known), str(missing)], "enabled": False},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"] == [
        {"chunk_id": str(known), "enabled": False, "reindex_required": False}
    ]
    assert body["not_found"] == [str(missing)]
    assert toggle.await_args.args[0] == [known, missing]
