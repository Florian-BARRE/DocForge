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
