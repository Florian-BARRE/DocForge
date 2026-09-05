"""Document explorer + blobs routers: NO-STORE locks — route registration and the path-param
422s FastAPI rejects before the handler body runs (so CONTEXT.database is never touched). The
store-backed behaviour (real 404s, metadata resolution, IR/chunk shapes, blob streaming) is
exercised live against the running stack — see the live verification in the delivery report.
"""


def test_explorer_and_blob_routes_are_registered(fastapi_app) -> None:
    """The read surface must be present in the API contract, with the right methods."""
    # The app wraps routers so app.routes is not flattened — the OpenAPI schema is the contract.
    paths = fastapi_app.openapi()["paths"]
    assert "get" in paths["/api/v1/collections/{collection_id}/documents"]
    assert "get" in paths["/api/v1/documents/{document_id}"]
    assert "delete" in paths["/api/v1/documents/{document_id}"]
    assert "get" in paths["/api/v1/documents/{document_id}/pages"]
    assert "get" in paths["/api/v1/documents/{document_id}/ir"]
    assert "get" in paths["/api/v1/documents/{document_id}/chunks"]
    assert "get" in paths["/api/v1/blobs/{content_hash}"]


def test_get_document_bad_uuid_is_422(client) -> None:
    """A non-UUID document id is rejected by FastAPI before the handler (no store touched)."""
    response = client.get("/api/v1/documents/not-a-uuid")
    assert response.status_code == 422, response.text


def test_list_documents_bad_collection_uuid_is_422(client) -> None:
    """A non-UUID collection id is rejected before the handler (no store touched)."""
    response = client.get("/api/v1/collections/not-a-uuid/documents")
    assert response.status_code == 422, response.text


def test_delete_document_bad_uuid_is_422(client) -> None:
    """A non-UUID document id on DELETE is rejected before the handler (no store touched)."""
    response = client.delete("/api/v1/documents/not-a-uuid")
    assert response.status_code == 422, response.text


def test_chunks_endpoint_returns_heading_path_and_resolved_page(
    client, fastapi_app, monkeypatch
) -> None:
    """GET /documents/{id}/chunks carries heading_path + the primary block's page (search-hit
    parity), so the explorer UI no longer reconstructs them."""
    import uuid  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415
    from unittest.mock import AsyncMock  # noqa: PLC0415

    from backend.context import CONTEXT  # noqa: PLC0415

    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    document = SimpleNamespace(id=doc_id, collection_id=uuid.uuid4())
    chunk = SimpleNamespace(
        id=chunk_id,
        chunk_index=0,
        text="body",
        token_count=2,
        is_indexed=True,
        strategy="recursive",
        parent_id=None,
        role="body",
        enabled_override=None,
        heading_path=["Chapter 1", "Overview"],
    )
    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_chunks=AsyncMock(return_value=[chunk]),
        get_document_chunk_composition=AsyncMock(return_value=[]),
        get_document_chunk_metadata=AsyncMock(return_value=[]),
        get_block_locations_for_chunks=AsyncMock(
            return_value={str(chunk_id): [{"block_id": "b1", "page": 7, "bbox": [0, 0, 1, 1]}]}
        ),
    )
    collections = SimpleNamespace(get_schema=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, collections=collections)
    )

    response = client.get(f"/api/v1/documents/{doc_id}/chunks")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["heading_path"] == ["Chapter 1", "Overview"]
    assert body[0]["page"] == 7
    documents.get_block_locations_for_chunks.assert_awaited_once_with([chunk_id])


def test_provenance_does_not_shadow_success_with_a_later_failed_run(
    client, fastapi_app, monkeypatch
) -> None:
    """A later FAILED re-ingest must not shadow the successful run that produced the persisted IR.

    Provenance resolves the latest DONE job (``get_latest_successful_for_document``), never the plain
    latest job — so a failed re-run queued after a successful ingest can never describe an IR it did
    not produce. The route must use the successful seam and report that DONE job's id + trace.
    """
    import uuid  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415
    from unittest.mock import AsyncMock  # noqa: PLC0415

    from backend.context import CONTEXT  # noqa: PLC0415

    doc_id = uuid.uuid4()
    successful_job_id = uuid.uuid4()
    failed_job_id = uuid.uuid4()
    document = SimpleNamespace(id=doc_id, collection_id=uuid.uuid4(), pipeline_version="v1")
    successful_job = SimpleNamespace(id=successful_job_id, document_id=doc_id)
    failed_job = SimpleNamespace(id=failed_job_id, document_id=doc_id)

    documents = SimpleNamespace(get=AsyncMock(return_value=document))
    jobs = SimpleNamespace(
        # The plain latest job is the FAILED re-run — the route must NOT pick this one.
        get_latest_for_document=AsyncMock(return_value=failed_job),
        # The latest DONE job is the earlier successful run — the provenance source of truth.
        get_latest_successful_for_document=AsyncMock(return_value=successful_job),
        list_events=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents, jobs=jobs))

    response = client.get(f"/api/v1/documents/{doc_id}/provenance")

    assert response.status_code == 200, response.text
    body = response.json()
    # The successful run is the provenance; the later FAILED run never shadows it.
    assert body["available"] is True
    assert body["job_id"] == str(successful_job_id)
    assert body["job_id"] != str(failed_job_id)
    jobs.get_latest_successful_for_document.assert_awaited_once_with(doc_id)
    jobs.get_latest_for_document.assert_not_awaited()
    jobs.list_events.assert_awaited_once_with(successful_job_id)
