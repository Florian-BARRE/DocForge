"""Collections CRUD against the REAL running API + Postgres: the full 11-field-type contract,
the enum/semantic guards (422, no store mutation), and PATCH rename/409/schema-diff/needs_reindex.

Every collection created here is deleted in a fixture ``finally`` — nothing survives the run.
"""

import uuid

import pytest

FIELD_TYPES = [
    "string", "integer", "float", "bool", "keyword_list", "datetime",
    "enum", "text", "integer_list", "float_list", "text_list",
]


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def temp_collection(api_client):
    """Creates collections via the real API and deletes every one of them afterwards."""
    created_ids: list[str] = []

    def _create(payload: dict) -> dict:
        response = api_client.post("/api/v1/collections", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        created_ids.append(body["id"])
        return body

    yield _create

    for collection_id in created_ids:
        api_client.delete(f"/api/v1/collections/{collection_id}")


def test_create_collection_with_all_eleven_field_types(api_client, temp_collection) -> None:
    fields = []
    for field_type in FIELD_TYPES:
        spec = {"field_name": f"f_{field_type}", "field_type": field_type}
        if field_type == "enum":
            spec["enum_values"] = ["alpha", "beta"]
        fields.append(spec)

    created = temp_collection({
        "name": _unique_name("all-types"),
        "supported_formats": ["pdf"],
        "max_file_size_bytes": 1_000_000,
        "fields": fields,
    })
    assert len(created["fields"]) == 11
    assert {f["field_type"] for f in created["fields"]} == set(FIELD_TYPES)

    fetched = api_client.get(f"/api/v1/collections/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert len(fetched.json()["fields"]) == 11


def test_enum_field_without_whitelist_is_422_and_nothing_is_created(api_client) -> None:
    name = _unique_name("bad-enum")
    response = api_client.post("/api/v1/collections", json={
        "name": name, "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
        "fields": [{"field_name": "status", "field_type": "enum"}],
    })
    assert response.status_code == 422, response.text
    assert (_find_by_name(api_client, name)) is None


def test_semantic_integer_list_field_is_422_and_nothing_is_created(api_client) -> None:
    name = _unique_name("bad-semantic")
    response = api_client.post("/api/v1/collections", json={
        "name": name, "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
        "fields": [{"field_name": "scores", "field_type": "integer_list", "semantic": True}],
    })
    assert response.status_code == 422, response.text
    assert (_find_by_name(api_client, name)) is None


def _find_by_name(api_client, name: str) -> dict | None:
    """No dedicated get-by-name route — scan the list (collections stay few in this suite)."""
    response = api_client.get("/api/v1/collections")
    assert response.status_code == 200, response.text
    return next((c for c in response.json() if c["name"] == name), None)


def test_patch_renames_the_collection(api_client, temp_collection) -> None:
    created = temp_collection({
        "name": _unique_name("rename-me"), "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
    })
    new_name = _unique_name("renamed")
    response = api_client.patch(f"/api/v1/collections/{created['id']}", json={"name": new_name})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == new_name


def test_patch_rename_to_an_existing_name_is_409(api_client, temp_collection) -> None:
    first = temp_collection({
        "name": _unique_name("taken"), "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
    })
    second = temp_collection({
        "name": _unique_name("renamer"), "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
    })
    response = api_client.patch(f"/api/v1/collections/{second['id']}", json={"name": first["name"]})
    assert response.status_code == 409, response.text


def test_patch_schema_change_to_searchable_flips_needs_reindex(api_client, temp_collection) -> None:
    created = temp_collection({
        "name": _unique_name("reindex"), "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
        "fields": [{"field_name": "topic", "field_type": "string"}],
    })
    assert created["needs_reindex"] is False

    response = api_client.patch(
        f"/api/v1/collections/{created['id']}",
        json={"fields": [{"field_name": "topic", "field_type": "string", "semantic": True}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["needs_reindex"] is True


def test_patch_unknown_collection_is_404(api_client) -> None:
    response = api_client.patch(f"/api/v1/collections/{uuid.uuid4()}", json={"name": "ghost"})
    assert response.status_code == 404, response.text


def test_delete_collection_then_get_is_404(api_client, temp_collection) -> None:
    created = temp_collection({
        "name": _unique_name("delete-me"), "supported_formats": ["pdf"], "max_file_size_bytes": 1_000_000,
    })
    delete_response = api_client.delete(f"/api/v1/collections/{created['id']}")
    assert delete_response.status_code == 204, delete_response.text

    get_response = api_client.get(f"/api/v1/collections/{created['id']}")
    assert get_response.status_code == 404, get_response.text

    # Idempotency: deleting again (or an unknown id) is still a clean 404, never a 500.
    again = api_client.delete(f"/api/v1/collections/{created['id']}")
    assert again.status_code == 404, again.text
