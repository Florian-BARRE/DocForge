"""Collections router: MODEL-LEVEL 422s — every case FastAPI/pydantic rejects before the
handler body ever runs, so no Postgres/store mocking is needed (CONTEXT.database is never
touched). Store-backed CRUD (name clash 409, schema diff, needs_reindex, delete) lives in
tests/live/ against the real stack — see [[port-scratchpad-gap-plan]].
"""

import uuid

import pytest
from fastapi import HTTPException


def test_create_collection_unknown_top_level_key_is_422(client) -> None:
    """extra="forbid": a typo'd request key must fail, never be silently dropped."""
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c1",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "piepline": {},  # typo of "pipeline"
        },
    )
    assert response.status_code == 422, response.text


def test_create_collection_unknown_field_spec_key_is_422(client) -> None:
    """A typo'd metadata-field flag (e.g. 'filterabl') must fail — a swallowed flag would build
    the wrong vector space silently."""
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c1",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "fields": [{"field_name": "jurisdiction", "field_type": "string", "filterabl": True}],
        },
    )
    assert response.status_code == 422, response.text


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


def test_create_collection_non_positive_job_timeout_is_422(client) -> None:
    """job_timeout_seconds is a wall-clock budget — a zero/negative value is nonsense (gt=0)."""
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c1",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "job_timeout_seconds": 0,
        },
    )
    assert response.status_code == 422, response.text


def test_update_collection_non_positive_job_timeout_is_422(client) -> None:
    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"job_timeout_seconds": -5},
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
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_fields(
            [FieldSpecModel(field_name="enabled", field_type="string")]
        )
    assert exc.value.status_code == 422
    assert "reserved" in exc.value.detail


def test_validate_fields_content_field_name_is_422(fastapi_app) -> None:
    """'content' is the search-target sentinel for the chunk body — reserved alongside the keys."""
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_fields(
            [FieldSpecModel(field_name="content", field_type="string")]
        )
    assert exc.value.status_code == 422
    assert "reserved" in exc.value.detail


def test_validate_fields_chunk_scope_non_generated_is_422(fastapi_app) -> None:
    """Chunk-scope values are produced by the pipeline — a user cannot declare them at upload."""
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_fields(
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
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_fields(
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


def test_validate_fields_enum_without_values_is_422(fastapi_app) -> None:
    """An enum field with no enum_values constrains nothing — the runtime coercion has no allowed
    set to check, so it must be rejected at declaration, not stored as an unvalidatable field."""
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_fields(
            [FieldSpecModel(field_name="doc_type", field_type="enum")]
        )
    assert exc.value.status_code == 422
    assert "enum_values" in exc.value.detail


def test_validate_fields_enum_with_empty_list_is_422(fastapi_app) -> None:
    """An explicitly EMPTY enum_values list is just as unusable as an omitted one — still a 422."""
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_fields(
            [FieldSpecModel(field_name="doc_type", field_type="enum", enum_values=[])]
        )
    assert exc.value.status_code == 422
    assert "enum_values" in exc.value.detail


def test_validate_fields_enum_with_values_does_not_raise(fastapi_app) -> None:
    """A properly declared enum (non-empty allowed set) passes the guard."""
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    CollectionHelpers.validate_fields(
        [FieldSpecModel(field_name="doc_type", field_type="enum", enum_values=["policy", "memo"])]
    )


def test_create_collection_enum_without_values_is_422(client) -> None:
    """The create endpoint surfaces the empty-enum guard as a 422 (not a stored broken field)."""
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "c-enum",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
            "fields": [{"field_name": "doc_type", "field_type": "enum"}],
        },
    )
    assert response.status_code == 422, response.text
    assert "enum_values" in response.text


def test_validate_fields_clean_field_does_not_raise(fastapi_app) -> None:
    """A well-formed document-scope field passes the guard without raising."""
    from backend.routers.collections.helpers import CollectionHelpers
    from backend.routers.collections.models import FieldSpecModel

    CollectionHelpers.validate_fields(
        [FieldSpecModel(field_name="author", field_type="string", filterable=True)]
    )


# ── contract-schema discovery: the identity/limits contract as JSON Schema (schema-driven UI) ──


def test_contract_schema_endpoint_returns_identity_limits_json_schema(client) -> None:
    """The discovery route serves the identity/limits contract as a JSON Schema the UI renders —
    a new scalar contract field auto-surfaces with zero frontend change (mirrors node config_schema).
    """
    response = client.get("/api/v1/collections/contract-schema")
    assert response.status_code == 200, response.text
    schema = response.json()["config_schema"]
    properties = schema["properties"]
    # The editable identity/limits scalars are present...
    assert "job_timeout_seconds" in properties
    assert {"name", "supported_formats", "max_file_size_bytes", "preset"} <= set(properties)
    # ...and the dedicated-editor surfaces (metadata schema + graph blobs) are NOT in this contract.
    assert "fields" not in properties
    assert "pipeline" not in properties
    assert "search" not in properties
