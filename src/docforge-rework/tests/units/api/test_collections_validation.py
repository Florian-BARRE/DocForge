"""Collections router: MODEL-LEVEL 422s — every case FastAPI/pydantic rejects before the
handler body ever runs, so no Postgres/store mocking is needed (CONTEXT.database is never
touched). Store-backed CRUD (name clash 409, schema diff, needs_reindex, delete) lives in
tests/live/ against the real stack — see [[port-scratchpad-gap-plan]].
"""

import uuid

import pytest
from fastapi import HTTPException


def test_create_collection_missing_required_name_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={"supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000},
    )
    assert response.status_code == 422, response.text


def test_create_collection_missing_required_supported_formats_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={"name": "c1", "max_file_size_bytes": 1_000_000},
    )
    assert response.status_code == 422, response.text


def test_create_collection_missing_required_max_file_size_bytes_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={"name": "c1", "supported_formats": ["pdf"]},
    )
    assert response.status_code == 422, response.text


def test_create_collection_wrong_type_for_max_file_size_bytes_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={"name": "c1", "supported_formats": ["pdf"], "max_file_size_bytes": "not-a-number"},
    )
    assert response.status_code == 422, response.text


def test_create_collection_unknown_field_type_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c1",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "fields": [{"field_name": "bogus", "field_type": "not_a_real_type"}],
        },
    )
    assert response.status_code == 422, response.text


def test_create_collection_unknown_origin_enum_member_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c1",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "fields": [
                {"field_name": "title", "field_type": "string", "origin": "not_a_real_origin"}
            ],
        },
    )
    assert response.status_code == 422, response.text


def test_create_collection_unknown_scope_enum_member_is_422(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c1",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "fields": [
                {"field_name": "title", "field_type": "string", "scope": "not_a_real_scope"}
            ],
        },
    )
    assert response.status_code == 422, response.text


def test_get_collection_invalid_uuid_path_param_is_422(client) -> None:
    response = client.get("/api/v1/collections/not-a-uuid")
    assert response.status_code == 422, response.text


def test_patch_collection_invalid_uuid_path_param_is_422(client) -> None:
    response = client.patch("/api/v1/collections/not-a-uuid", json={"name": "new-name"})
    assert response.status_code == 422, response.text


def test_delete_collection_invalid_uuid_path_param_is_422(client) -> None:
    response = client.delete("/api/v1/collections/not-a-uuid")
    assert response.status_code == 422, response.text


def test_patch_collection_unknown_field_type_in_fields_is_422(client) -> None:
    """A well-formed UUID path param, but a broken fields payload — still rejected at the
    model layer, before the handler ever calls CONTEXT.database.collections.get()."""
    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"fields": [{"field_name": "x", "field_type": "still_not_real"}]},
    )
    assert response.status_code == 422, response.text


# ── _validate_fields guards (store-free: called directly, so no name-clash / DB dependency) ──
# `fastapi_app` registers app/ on sys.path; the `backend` imports are deferred until then.


def test_validate_fields_reserved_payload_key_name_is_422(fastapi_app) -> None:
    """A field named after a reserved chunk-payload key would overwrite it when denormalised."""
    from backend.routers.collections.models import FieldSpecModel
    from backend.routers.collections.router import _validate_fields

    with pytest.raises(HTTPException) as exc:
        _validate_fields([FieldSpecModel(field_name="enabled", field_type="string")])
    assert exc.value.status_code == 422
    assert "reserved" in exc.value.detail


def test_validate_fields_content_field_name_is_422(fastapi_app) -> None:
    """'content' is the search-target sentinel for the chunk body — reserved alongside the keys."""
    from backend.routers.collections.models import FieldSpecModel
    from backend.routers.collections.router import _validate_fields

    with pytest.raises(HTTPException) as exc:
        _validate_fields([FieldSpecModel(field_name="content", field_type="string")])
    assert exc.value.status_code == 422
    assert "reserved" in exc.value.detail


def test_validate_fields_chunk_scope_non_generated_is_422(fastapi_app) -> None:
    """Chunk-scope values are produced by the pipeline — a user cannot declare them at upload."""
    from backend.routers.collections.models import FieldSpecModel
    from backend.routers.collections.router import _validate_fields

    with pytest.raises(HTTPException) as exc:
        _validate_fields(
            [
                FieldSpecModel(
                    field_name="summary", field_type="string", scope="chunk", origin="user"
                )
            ]
        )
    assert exc.value.status_code == 422
    assert "chunk scope" in exc.value.detail


def test_validate_fields_chunk_scope_lexical_is_422(fastapi_app) -> None:
    """No BM25 producer exists for chunk-scope metadata — reject up front, not silent-empty search."""
    from backend.routers.collections.models import FieldSpecModel
    from backend.routers.collections.router import _validate_fields

    with pytest.raises(HTTPException) as exc:
        _validate_fields(
            [
                FieldSpecModel(
                    field_name="tag",
                    field_type="string",
                    scope="chunk",
                    origin="generated",
                    lexical=True,
                )
            ]
        )
    assert exc.value.status_code == 422
    assert "lexical" in exc.value.detail


def test_validate_fields_clean_field_does_not_raise(fastapi_app) -> None:
    """A well-formed document-scope field passes the guard without raising."""
    from backend.routers.collections.models import FieldSpecModel
    from backend.routers.collections.router import _validate_fields

    _validate_fields([FieldSpecModel(field_name="author", field_type="string", filterable=True)])
