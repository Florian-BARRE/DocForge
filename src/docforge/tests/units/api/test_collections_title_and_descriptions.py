"""Agent-UX schema settings on the collections surface (wave A).

Pins:
  1. field ``description`` — accepted on FieldSpecModel (bounded), NUL-stripped/blank→None on write,
     read back on the contract, applied by the schema diff, and NEVER a reindex trigger (the index
     signature ignores it);
  2. ``title_field`` — validated against the post-write schema's DOCUMENT-scope fields (422 naming the
     valid choices), explicit null clears, omitted leaves it alone, and a schema diff that orphans it
     clears it in the same transaction;
  3. the constant secret mask — no key character leaks, and BOTH the new constant and the legacy
     ``__redacted__<last4>`` form round-trip to the stored key.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from shared_libs.pipelines.blob_secrets import (
    MASK,
    MASK_PREFIX,
    redact_blob_secrets,
    restore_blob_secrets,
)
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import CollectionUpdateResult
from shared_libs.services.db.facades import collections_facade as cf_module
from shared_libs.services.db.facades.collections_facade import CollectionsFacade
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql.tables import MetadataField

SECRET = "sk-live-ABCDEFGH-9876"


def _row(name: str, *, scope=FieldScope.DOCUMENT, description=None, semantic=False):
    """A transient metadata_field row."""
    return MetadataField(
        field_name=name,
        field_type=FieldType.STRING,
        required=False,
        filterable=False,
        lexical=False,
        semantic=semantic,
        enum_values=None,
        origin=FieldOrigin.USER if scope == FieldScope.DOCUMENT else FieldOrigin.GENERATED,
        scope=scope,
        description=description,
    )


def _fake_collection(**overrides) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(),
        name="c1",
        supported_formats=["pdf"],
        tags=[],
        max_file_size_bytes=1_000_000,
        job_timeout_seconds=None,
        needs_reindex=False,
        created_at=None,
        pipeline={},
        search={},
        title_field=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _mock_db(monkeypatch, **methods) -> SimpleNamespace:
    from backend.context import CONTEXT  # noqa: PLC0415

    facade = SimpleNamespace(**methods)
    schema_changes = SimpleNamespace(
        count_field_values=AsyncMock(return_value={}), purge_departed_fields=AsyncMock()
    )
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=facade, schema_changes=schema_changes)
    )
    return facade


# ─────────────────────────── description ───────────────────────────


def test_field_spec_description_is_bounded(fastapi_app) -> None:
    from backend.routers.collections.models import FieldSpecModel  # noqa: PLC0415

    FieldSpecModel(field_name="a", field_type="string", description="x" * 1000)
    with pytest.raises(ValidationError):
        FieldSpecModel(field_name="a", field_type="string", description="x" * 1001)


def test_description_write_is_nul_stripped_and_blank_is_none(fastapi_app) -> None:
    from backend.routers.collections.helpers import CollectionHelpers  # noqa: PLC0415
    from backend.routers.collections.models import FieldSpecModel  # noqa: PLC0415

    rows = CollectionHelpers.to_field_rows(
        [
            FieldSpecModel(field_name="a", field_type="string", description=" Au\x00thor "),
            FieldSpecModel(field_name="b", field_type="string", description="   "),
            FieldSpecModel(field_name="c", field_type="string"),
        ]
    )
    assert [row.description for row in rows] == ["Author", None, None]


def test_description_and_title_field_are_read_back(client, monkeypatch) -> None:
    fake = _fake_collection(title_field="topic")
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_schema=AsyncMock(return_value=[_row("topic", description="Business process")]),
    )
    response = client.get(f"/api/v1/collections/{fake.id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title_field"] == "topic"
    assert payload["fields"][0]["description"] == "Business process"


def test_index_signature_ignores_description() -> None:
    blob = {"nodes": []}
    before = CollectionIndexSignature.compute(blob, [_row("t", semantic=True, description=None)])
    after = CollectionIndexSignature.compute(blob, [_row("t", semantic=True, description="new")])
    assert before == after


async def test_schema_diff_applies_a_description_only_change(monkeypatch) -> None:
    stored = _row("topic", semantic=True)
    monkeypatch.setattr(cf_module.CollectionApi, "get_schema", AsyncMock(return_value=[stored]))
    session = MagicMock()

    await CollectionsFacade._apply_schema_diff(
        session, uuid.uuid4(), [_row("topic", semantic=True, description="What it means")]
    )

    assert stored.description == "What it means"
    session.add.assert_not_called()  # an in-place field update, not a new row


# ─────────────────────────── title_field: validation ───────────────────────────


def test_patch_title_field_must_be_a_document_scope_field(client, monkeypatch) -> None:
    fake = _fake_collection()
    apply_update = AsyncMock()
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_schema=AsyncMock(
            return_value=[_row("author"), _row("summary", scope=FieldScope.CHUNK)]
        ),
        apply_update=apply_update,
    )
    for bad in ("nope", "summary"):
        response = client.patch(f"/api/v1/collections/{fake.id}", json={"title_field": bad})
        assert response.status_code == 422, response.text
        assert "['author']" in response.text  # names the valid choices
    apply_update.assert_not_called()


def test_patch_title_field_set_clear_and_omit(client, monkeypatch) -> None:
    fake = _fake_collection()
    apply_update = AsyncMock(
        return_value=CollectionUpdateResult(schema_applied=False, schema_reindex_required=False)
    )
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_by_name=AsyncMock(return_value=None),
        get_schema=AsyncMock(return_value=[_row("author")]),
        apply_update=apply_update,
    )
    url = f"/api/v1/collections/{fake.id}"

    assert client.patch(url, json={"title_field": "author"}).status_code == 200
    spec = apply_update.await_args.args[1]
    assert (spec.apply_title_field, spec.title_field) == (True, "author")

    assert client.patch(url, json={"title_field": None}).status_code == 200
    spec = apply_update.await_args.args[1]
    assert (spec.apply_title_field, spec.title_field) == (True, None)

    assert client.patch(url, json={"name": "c1"}).status_code == 200
    assert apply_update.await_args.args[1].apply_title_field is False


def test_patch_title_field_validates_against_the_new_fields(client, monkeypatch) -> None:
    fake = _fake_collection()
    apply_update = AsyncMock(
        return_value=CollectionUpdateResult(schema_applied=True, schema_reindex_required=False)
    )
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_by_name=AsyncMock(return_value=None),
        get_schema=AsyncMock(return_value=[_row("author")]),
        apply_update=apply_update,
        reconcile_store=AsyncMock(return_value=set()),
    )
    from backend.context import CONTEXT  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT, "queue", SimpleNamespace(enqueue_backfill=AsyncMock()), raising=False
    )
    url = f"/api/v1/collections/{fake.id}"
    # "author" is being removed by this same PATCH → it is no longer a valid choice.
    body = {"fields": [{"field_name": "region", "field_type": "string"}], "title_field": "author"}
    assert client.patch(url, json=body).status_code == 422
    body["title_field"] = "region"
    assert client.patch(url, json=body).status_code == 200, "a field added by the PATCH is valid"


def test_create_rejects_an_unknown_title_field_before_any_store_touch(client, monkeypatch) -> None:
    facade = _mock_db(monkeypatch, get_by_name=AsyncMock(return_value=None), create=AsyncMock())
    response = client.post(
        "/api/v1/collections",
        json={
            "name": "x",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1000,
            "fields": [{"field_name": "author", "field_type": "string"}],
            "title_field": "missing",
        },
    )
    assert response.status_code == 422, response.text
    assert "['author']" in response.text
    facade.create.assert_not_called()


# ─────────────────────────── title_field: cleared when orphaned ───────────────────────────


def _session_facade() -> CollectionsFacade:
    @asynccontextmanager
    async def _session():
        yield MagicMock()

    postgres = MagicMock()
    postgres.session = _session
    return CollectionsFacade(postgres, MagicMock(), MagicMock())


@pytest.mark.parametrize(
    ("schema", "expected_cleared"),
    [
        ([_row("region")], "author"),  # field removed / renamed
        ([_row("author", scope=FieldScope.CHUNK)], "author"),  # moved to chunk scope
        ([_row("author")], None),  # still valid → kept
    ],
)
async def test_orphaned_title_field_is_cleared(monkeypatch, schema, expected_cleared) -> None:
    collection = SimpleNamespace(title_field="author")
    monkeypatch.setattr(cf_module.CollectionApi, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(cf_module.CollectionApi, "get_schema", AsyncMock(return_value=schema))

    cleared = await _session_facade()._clear_orphaned_title_field(MagicMock(), uuid.uuid4())

    assert cleared == expected_cleared
    assert collection.title_field == (None if expected_cleared else "author")


async def test_schema_patch_runs_the_orphan_clear(monkeypatch) -> None:
    from shared_libs.services.db.facades import CollectionUpdateSpec  # noqa: PLC0415

    monkeypatch.setattr(cf_module.DatabaseHelpers, "validate_vector_slugs", lambda _f: None)
    monkeypatch.setattr(cf_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(cf_module.CollectionApi, "touch", AsyncMock())
    collection = SimpleNamespace(title_field="author", pipeline={}, indexed_signature=None)
    monkeypatch.setattr(cf_module.CollectionApi, "get", AsyncMock(return_value=collection))

    await _session_facade().apply_update(uuid.uuid4(), CollectionUpdateSpec(schema_fields=[]))

    assert collection.title_field is None


async def test_title_field_write_runs_the_orphan_clear_in_the_same_transaction(monkeypatch) -> None:
    """The router validates title_field OUTSIDE the write transaction; a concurrent schema PATCH can
    drop the field in between — the title write itself must re-check it inside the transaction."""
    from shared_libs.services.db.facades import CollectionUpdateSpec  # noqa: PLC0415

    collection = SimpleNamespace(title_field=None)

    async def _set(_session, _cid, value):
        collection.title_field = value

    monkeypatch.setattr(cf_module.CollectionApi, "set_title_field", AsyncMock(side_effect=_set))
    monkeypatch.setattr(cf_module.CollectionApi, "get", AsyncMock(return_value=collection))
    # The field vanished (concurrent schema PATCH) between validation and this write.
    monkeypatch.setattr(cf_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))

    spec = CollectionUpdateSpec(apply_title_field=True, title_field="author")
    await _session_facade().apply_update(uuid.uuid4(), spec)

    assert collection.title_field is None


# ─────────────────────────── secrets: constant mask ───────────────────────────


def _blob(api_key: str) -> dict:
    return {
        "nodes": [
            {"node_type": "action", "id": "llm1", "family": "llm", "config": {"api_key": api_key}}
        ]
    }


def test_mask_is_a_constant_with_no_key_character() -> None:
    masked = redact_blob_secrets(_blob(SECRET))["nodes"][0]["config"]["api_key"]
    assert masked == MASK == MASK_PREFIX
    assert SECRET[-4:] not in masked


@pytest.mark.parametrize(
    "echoed", [MASK, f"{MASK_PREFIX}{SECRET[-4:]}"], ids=["constant", "legacy"]
)
def test_both_mask_forms_round_trip_to_the_stored_key(echoed: str) -> None:
    healed = restore_blob_secrets(_blob(echoed), _blob(SECRET))
    assert healed["nodes"][0]["config"]["api_key"] == SECRET


def test_get_collection_leaks_no_secret_character(client, monkeypatch) -> None:
    fake = _fake_collection(pipeline=_blob(SECRET), search=_blob(SECRET))
    _mock_db(monkeypatch, get=AsyncMock(return_value=fake), get_schema=AsyncMock(return_value=[]))
    response = client.get(f"/api/v1/collections/{fake.id}")
    assert response.status_code == 200, response.text
    assert SECRET not in response.text
    assert SECRET[-4:] not in response.text
    assert response.json()["pipeline"]["nodes"][0]["config"]["api_key"] == MASK
