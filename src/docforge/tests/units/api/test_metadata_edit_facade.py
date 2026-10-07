"""MetadataEditFacade (document metadata value-edit) + DocumentApi.update_metadata.

All serviceless: Postgres/Qdrant are mocked (pattern from test_filter_sync_facade.py). The tests
prove WHAT is validated, WHAT is written, and WHICH changed fields trigger a re-embed — never a
real store. DocumentApi.update_metadata is exercised directly against a statement-capturing fake
session so the NUL-strip + ON CONFLICT upsert shape is asserted without a live database.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import (
    MetadataEditFacade,
    MetadataEditNotFoundError,
    MetadataValidationError,
)
from shared_libs.services.db.facades import metadata_edit_facade as mef
from shared_libs.services.db.postgresql.apis import DocumentApi
from shared_libs.services.db.postgresql.tables import DocumentMetadata


# -------------------- helpers --------------------
def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _field(
    *,
    field_id: int,
    name: str,
    field_type: FieldType = FieldType.STRING,
    scope: FieldScope = FieldScope.DOCUMENT,
    origin: FieldOrigin = FieldOrigin.USER,
    filterable: bool = False,
    lexical: bool = False,
    semantic: bool = False,
    enum_values: list[str] | None = None,
) -> SimpleNamespace:
    """A stand-in metadata_field schema row carrying only what the facade reads."""
    return SimpleNamespace(
        id=field_id,
        field_name=name,
        field_type=field_type,
        required=False,
        filterable=filterable,
        lexical=lexical,
        semantic=semantic,
        origin=origin,
        scope=scope,
        enum_values=enum_values,
    )


def _qdrant_stub() -> MagicMock:
    """A qdrant client stub exposing the ``.raw`` the facade hands to QdrantIndexApi."""
    qdrant = MagicMock()
    qdrant.raw = MagicMock()
    return qdrant


def _facade_with_schema(monkeypatch, schema: list[SimpleNamespace], filter_sync: MagicMock):
    """Build a MetadataEditFacade whose DB reads resolve to ``schema`` and a stub filter-sync."""
    document = MagicMock(id=uuid.uuid4(), collection_id=uuid.uuid4())
    monkeypatch.setattr(mef.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(mef.CollectionApi, "get_schema", AsyncMock(return_value=schema))
    monkeypatch.setattr(mef.DocumentApi, "update_metadata", AsyncMock())
    monkeypatch.setattr(mef.DocumentApi, "delete_metadata", AsyncMock())
    monkeypatch.setattr(mef.DocumentApi, "touch", AsyncMock())
    # Default: nothing stored yet → every requested SET field reads as changed (a CLEAR of an absent
    # field is a no-op). Tests exercising change-detection / clears re-stub get_metadata with the
    # stored rows they want to compare to.
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", AsyncMock(return_value=[]))
    # The two clear primitives are store writes — mocked so a clear asserts the CALL, not a live op.
    monkeypatch.setattr(mef.QdrantIndexApi, "delete_payload", AsyncMock())
    monkeypatch.setattr(mef.QdrantIndexApi, "delete_vectors", AsyncMock())
    facade = MetadataEditFacade(_postgres_yielding(MagicMock()), filter_sync, _qdrant_stub())
    return facade, document


class _CapturingSession:
    """A fake session that records the SQLAlchemy statements passed to execute()."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    async def execute(self, statement: object) -> None:
        self.statements.append(statement)


# -------------------- DocumentApi.update_metadata --------------------
async def test_update_metadata_noop_when_empty() -> None:
    """An empty change set issues NO statement (nothing to upsert)."""
    session = _CapturingSession()
    await DocumentApi.update_metadata(session, uuid.uuid4(), [])
    assert session.statements == []


async def test_update_metadata_strips_nul_and_is_an_upsert() -> None:
    """The scalar value is NUL-stripped and the statement is an ON CONFLICT DO UPDATE upsert."""
    session = _CapturingSession()
    rows = [DocumentMetadata(field_id=7, value="a\x00b", origin=FieldOrigin.USER)]

    await DocumentApi.update_metadata(session, uuid.uuid4(), rows)

    assert len(session.statements) == 1
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    values = list(compiled.params.values())
    # 1. The NUL is gone, the stripped value is what gets written.
    assert "a\x00b" not in values
    assert "ab" in values
    # 2. It is an upsert on the (document_id, field_id) unique key, not a plain insert.
    assert "ON CONFLICT" in str(compiled).upper()


async def test_update_metadata_strips_nul_inside_list_value() -> None:
    """A NUL buried in a list value (keyword_list) is stripped too (recursive sanitize)."""
    session = _CapturingSession()
    rows = [DocumentMetadata(field_id=3, value=["x\x00y", "z"], origin=FieldOrigin.GENERATED)]

    await DocumentApi.update_metadata(session, uuid.uuid4(), rows)

    values = list(session.statements[0].compile(dialect=postgresql.dialect()).params.values())
    assert ["xy", "z"] in values


# -------------------- DocumentApi.delete_metadata --------------------
async def test_delete_metadata_noop_when_empty() -> None:
    """An empty field-id set issues NO statement (nothing to delete)."""
    session = _CapturingSession()
    await DocumentApi.delete_metadata(session, uuid.uuid4(), [])
    assert session.statements == []


async def test_delete_metadata_targets_only_the_listed_fields() -> None:
    """The DELETE is scoped to the (document_id, field_id IN (...)) rows, nothing else."""
    session = _CapturingSession()

    await DocumentApi.delete_metadata(session, uuid.uuid4(), [4, 9])

    assert len(session.statements) == 1
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect())).upper()
    assert "DELETE FROM" in compiled
    assert "DOCUMENT_ID" in compiled and "FIELD_ID IN" in compiled


# -------------------- facade validation --------------------
async def test_unknown_field_raises_validation_error(monkeypatch) -> None:
    schema = [_field(field_id=1, name="topic")]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    with pytest.raises(MetadataValidationError) as excinfo:
        await facade.update_document_metadata(document.id, {"nope": "x"})

    assert any("unknown field 'nope'" in message for message in excinfo.value.errors)
    mef.DocumentApi.update_metadata.assert_not_awaited()
    filter_sync.sync_document_filter_payloads.assert_not_awaited()


async def test_chunk_scope_field_is_rejected(monkeypatch) -> None:
    """A chunk-scope field has no cheap value-edit path — it is a 422-mapping validation error."""
    schema = [
        _field(field_id=1, name="sentiment", scope=FieldScope.CHUNK, origin=FieldOrigin.GENERATED)
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    with pytest.raises(MetadataValidationError) as excinfo:
        await facade.update_document_metadata(document.id, {"sentiment": "positive"})

    assert any("chunk-scope" in message for message in excinfo.value.errors)
    mef.DocumentApi.update_metadata.assert_not_awaited()


async def test_bad_value_type_is_rejected(monkeypatch) -> None:
    """A value whose shape does not match the field type fails validation (reuses value_error)."""
    schema = [_field(field_id=1, name="year", field_type=FieldType.INTEGER)]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    with pytest.raises(MetadataValidationError):
        await facade.update_document_metadata(document.id, {"year": "not-an-int"})


async def test_accepts_user_and_generated_document_scope(monkeypatch) -> None:
    """Both a USER and a GENERATED document-scope field are accepted and written + filter-synced."""
    schema = [
        _field(field_id=1, name="topic", origin=FieldOrigin.USER, filterable=True),
        _field(field_id=2, name="summary", origin=FieldOrigin.GENERATED),
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock(return_value=3))
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    result = await facade.update_document_metadata(
        document.id, {"topic": "ai", "summary": "a recap"}
    )

    assert result.updated_fields == ["summary", "topic"]
    assert result.reembed_fields == []  # neither field is semantic/lexical
    mef.DocumentApi.update_metadata.assert_awaited_once()
    filter_sync.sync_document_filter_payloads.assert_awaited_once_with(document.id)


async def test_reembed_fields_only_for_semantic_or_lexical(monkeypatch) -> None:
    """Only a changed semantic/lexical field lands in reembed_fields; filterable-only is excluded."""
    schema = [
        _field(field_id=1, name="topic", filterable=True),
        _field(field_id=2, name="abstract", semantic=True),
        _field(field_id=3, name="tags", field_type=FieldType.KEYWORD_LIST, lexical=True),
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock(return_value=1))
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    result = await facade.update_document_metadata(
        document.id, {"topic": "ai", "abstract": "an abstract", "tags": ["a", "b"]}
    )

    assert result.reembed_fields == ["abstract", "tags"]


async def test_unchanged_value_is_a_noop(monkeypatch) -> None:
    """Re-sending a field's current value changes nothing: no write statement, no filter sync, no
    re-embed — the whole point is not to spend on an edit that edits nothing."""
    schema = [_field(field_id=1, name="topic", filterable=True, semantic=True)]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    # The stored value already equals what the caller re-sends.
    monkeypatch.setattr(
        mef.DocumentApi,
        "get_metadata",
        AsyncMock(return_value=[SimpleNamespace(field_id=1, value="ai")]),
    )

    result = await facade.update_document_metadata(document.id, {"topic": "ai"})

    assert result.updated_fields == []
    assert result.reembed_fields == []
    assert result.filter_repaint_failed is False
    filter_sync.sync_document_filter_payloads.assert_not_awaited()
    # update_metadata is still awaited, but with an EMPTY change set (which itself no-ops).
    _, _, changed = mef.DocumentApi.update_metadata.await_args.args
    assert changed == []


async def test_only_changed_fields_are_written(monkeypatch) -> None:
    """With one field unchanged and one changed, only the changed field is written + reported."""
    schema = [
        _field(field_id=1, name="topic", filterable=True),
        _field(field_id=2, name="summary"),
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock(return_value=2))
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(
        mef.DocumentApi,
        "get_metadata",
        AsyncMock(return_value=[SimpleNamespace(field_id=1, value="ai")]),  # topic unchanged
    )

    result = await facade.update_document_metadata(
        document.id, {"topic": "ai", "summary": "new recap"}
    )

    assert result.updated_fields == ["summary"]
    _, _, changed = mef.DocumentApi.update_metadata.await_args.args
    assert [row.field_id for row in changed] == [2]
    filter_sync.sync_document_filter_payloads.assert_awaited_once_with(document.id)


async def test_filter_repaint_failure_is_best_effort(monkeypatch) -> None:
    """A Qdrant hiccup on the inline filterable repaint must NOT raise (the PG write is committed) —
    the result flags it so the caller schedules the durable repair job."""
    schema = [_field(field_id=1, name="topic", filterable=True)]
    filter_sync = SimpleNamespace(
        sync_document_filter_payloads=AsyncMock(side_effect=RuntimeError("qdrant down"))
    )
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    result = await facade.update_document_metadata(document.id, {"topic": "ai"})

    assert result.updated_fields == ["topic"]
    assert result.filter_repaint_failed is True  # caller must enqueue the repair


async def test_missing_document_raises_not_found(monkeypatch) -> None:
    monkeypatch.setattr(mef.DocumentApi, "get", AsyncMock(return_value=None))
    facade = MetadataEditFacade(
        _postgres_yielding(MagicMock()),
        SimpleNamespace(sync_document_filter_payloads=AsyncMock()),
        _qdrant_stub(),
    )

    with pytest.raises(MetadataEditNotFoundError):
        await facade.update_document_metadata(uuid.uuid4(), {"topic": "ai"})


# -------------------- clearing a value (null) --------------------
async def test_clear_filterable_field_deletes_payload_key_no_job(monkeypatch) -> None:
    """Clearing a filterable field deletes its PG row AND its Qdrant payload key; never a re-embed."""
    schema = [_field(field_id=1, name="topic", filterable=True)]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    # The field currently holds a value, so clearing it is a real change (not a no-op).
    monkeypatch.setattr(
        mef.DocumentApi,
        "get_metadata",
        AsyncMock(return_value=[SimpleNamespace(field_id=1, value="ai")]),
    )

    result = await facade.update_document_metadata(document.id, {"topic": None})

    # 1. Reported as cleared, never re-embedded (a clear needs no embed → no worker job).
    assert result.updated_fields == ["topic"]
    assert result.reembed_fields == []
    # 2. The PG row is deleted and the filterable payload key removed under the EXACT field name.
    _, _, cleared_ids = mef.DocumentApi.delete_metadata.await_args.args
    assert cleared_ids == [1]
    keys = mef.QdrantIndexApi.delete_payload.await_args.args[2]
    assert keys == ["topic"]
    # 3. No semantic/lexical vector to drop for a filterable-only field.
    assert mef.QdrantIndexApi.delete_vectors.await_args.args[2] == []
    # 4. A SET repaint never ran (nothing was set).
    filter_sync.sync_document_filter_payloads.assert_not_awaited()


async def test_clear_semantic_lexical_field_deletes_both_named_vectors(monkeypatch) -> None:
    """Clearing a semantic+lexical field drops both its named vectors; row deleted; no re-embed."""
    schema = [
        _field(field_id=2, name="abstract", semantic=True, lexical=True),
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(
        mef.DocumentApi,
        "get_metadata",
        AsyncMock(return_value=[SimpleNamespace(field_id=2, value="an abstract")]),
    )

    result = await facade.update_document_metadata(document.id, {"abstract": None})

    assert result.updated_fields == ["abstract"]
    assert result.reembed_fields == []
    vector_names = mef.QdrantIndexApi.delete_vectors.await_args.args[2]
    assert vector_names == [
        mef.VectorNames.field_dense("abstract"),
        mef.VectorNames.field_sparse("abstract"),
    ]
    # No filterable key to drop for a semantic/lexical-only field.
    assert mef.QdrantIndexApi.delete_payload.await_args.args[2] == []


async def test_clear_required_field_is_rejected(monkeypatch) -> None:
    """A required field cannot be cleared — null on it is a 422-mapping validation error."""
    schema = [_field(field_id=1, name="topic", filterable=True)]
    schema[0].required = True
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)

    with pytest.raises(MetadataValidationError) as excinfo:
        await facade.update_document_metadata(document.id, {"topic": None})

    assert any(
        "required" in message and "cannot be cleared" in message for message in excinfo.value.errors
    )
    mef.DocumentApi.delete_metadata.assert_not_awaited()


async def test_clear_already_absent_field_is_a_noop(monkeypatch) -> None:
    """Clearing a field that has no stored value changes nothing — not in updated_fields, no store op."""
    schema = [_field(field_id=1, name="topic", filterable=True)]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    # Nothing stored (default get_metadata -> []), so there is nothing to clear.

    result = await facade.update_document_metadata(document.id, {"topic": None})

    assert result.updated_fields == []
    assert result.reembed_fields == []
    _, _, cleared_ids = mef.DocumentApi.delete_metadata.await_args.args
    assert cleared_ids == []
    mef.QdrantIndexApi.delete_payload.assert_not_awaited()
    mef.QdrantIndexApi.delete_vectors.assert_not_awaited()


async def test_mixed_set_and_clear_in_one_patch(monkeypatch) -> None:
    """A SET and a CLEAR in one PATCH: the SET enqueues (semantic), the CLEAR is synchronous; both
    land in updated_fields."""
    schema = [
        _field(field_id=1, name="topic", filterable=True),  # cleared
        _field(field_id=2, name="abstract", semantic=True),  # set (needs re-embed)
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock(return_value=1))
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(
        mef.DocumentApi,
        "get_metadata",
        AsyncMock(return_value=[SimpleNamespace(field_id=1, value="ai")]),  # topic has a value
    )

    result = await facade.update_document_metadata(
        document.id, {"topic": None, "abstract": "a new abstract"}
    )

    # 1. Both the set and the cleared field are reported; only the SET semantic field re-embeds.
    assert result.updated_fields == ["abstract", "topic"]
    assert result.reembed_fields == ["abstract"]
    # 2. The clear is handled synchronously: PG row deleted + payload key dropped.
    _, _, cleared_ids = mef.DocumentApi.delete_metadata.await_args.args
    assert cleared_ids == [1]
    assert mef.QdrantIndexApi.delete_payload.await_args.args[2] == ["topic"]
    # 3. The SET repaint ran for the changed filterable set (abstract is semantic-only here).
    filter_sync.sync_document_filter_payloads.assert_awaited_once_with(document.id)


# -------------------- clear path: edges, best-effort, atomicity --------------------
def _stored(*pairs: tuple[int, object]) -> AsyncMock:
    """A get_metadata stub returning the given (field_id, value) pairs as stored rows."""
    return AsyncMock(
        return_value=[SimpleNamespace(field_id=fid, value=value) for fid, value in pairs]
    )


async def test_clear_hits_qdrant_with_raw_client_collection_and_document(monkeypatch) -> None:
    """Both primitives receive (raw client, the collection's Qdrant name, keys/names, document id)."""
    schema = [_field(field_id=1, name="topic", filterable=True, semantic=True)]
    facade, document = _facade_with_schema(
        monkeypatch, schema, SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    )
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "ai")))

    await facade.update_document_metadata(document.id, {"topic": None})

    expected_name = mef.DatabaseHelpers.qdrant_collection_name(document.collection_id)
    raw = facade._qdrant.raw
    mef.QdrantIndexApi.delete_payload.assert_awaited_once_with(
        raw, expected_name, ["topic"], document.id
    )
    mef.QdrantIndexApi.delete_vectors.assert_awaited_once_with(
        raw, expected_name, [mef.VectorNames.field_dense("topic")], document.id
    )


async def test_clear_lexical_only_field_drops_only_the_sparse_vector(monkeypatch) -> None:
    schema = [_field(field_id=3, name="tags", field_type=FieldType.KEYWORD_LIST, lexical=True)]
    facade, document = _facade_with_schema(
        monkeypatch, schema, SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    )
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((3, ["a"])))

    await facade.update_document_metadata(document.id, {"tags": None})

    assert mef.QdrantIndexApi.delete_vectors.await_args.args[2] == [
        mef.VectorNames.field_sparse("tags")
    ]
    assert mef.QdrantIndexApi.delete_payload.await_args.args[2] == []


async def test_clear_with_no_footprint_flags_still_reports_the_field(monkeypatch) -> None:
    """A field with no filterable/semantic/lexical flag has no Qdrant footprint: the PG row is deleted
    and reported, both primitives get empty lists (they no-op), nothing flags a repair."""
    schema = [_field(field_id=1, name="note")]
    facade, document = _facade_with_schema(
        monkeypatch, schema, SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    )
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "x")))

    result = await facade.update_document_metadata(document.id, {"note": None})

    assert result.updated_fields == ["note"]
    assert result.filter_repaint_failed is False
    assert mef.QdrantIndexApi.delete_payload.await_args.args[2] == []
    assert mef.QdrantIndexApi.delete_vectors.await_args.args[2] == []


@pytest.mark.parametrize("failing", ["delete_payload", "delete_vectors"])
async def test_clear_qdrant_failure_is_best_effort_and_flags_repair(monkeypatch, failing) -> None:
    """A Qdrant hiccup removing the footprint must NOT raise (the PG delete is committed): the cleared
    field is still reported and the result flags the repair so the caller schedules the durable job."""
    schema = [_field(field_id=1, name="topic", filterable=True, semantic=True)]
    facade, document = _facade_with_schema(
        monkeypatch, schema, SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    )
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "ai")))
    monkeypatch.setattr(
        mef.QdrantIndexApi, failing, AsyncMock(side_effect=RuntimeError("qdrant down"))
    )

    result = await facade.update_document_metadata(document.id, {"topic": None})

    assert result.updated_fields == ["topic"]
    assert result.reembed_fields == []
    assert result.filter_repaint_failed is True
    # The PG delete ran before the Qdrant step (it is the source of truth).
    _, _, cleared_ids = mef.DocumentApi.delete_metadata.await_args.args
    assert cleared_ids == [1]


async def test_clear_failure_does_not_skip_the_set_repaint_flag_merge(monkeypatch) -> None:
    """Mixed patch where the SET repaint SUCCEEDS but the CLEAR removal FAILS: the failure flag is
    OR-ed (not overwritten by the later/earlier success)."""
    schema = [
        _field(field_id=1, name="topic", filterable=True),  # cleared
        _field(field_id=2, name="year", field_type=FieldType.INTEGER, filterable=True),  # set
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock(return_value=1))
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "ai")))
    monkeypatch.setattr(
        mef.QdrantIndexApi, "delete_payload", AsyncMock(side_effect=RuntimeError("down"))
    )

    result = await facade.update_document_metadata(document.id, {"topic": None, "year": 2024})

    assert result.updated_fields == ["topic", "year"]
    assert result.filter_repaint_failed is True
    filter_sync.sync_document_filter_payloads.assert_awaited_once_with(document.id)


async def test_set_repaint_failure_still_clears_the_footprint(monkeypatch) -> None:
    """The opposite merge: a failed SET repaint must not prevent the CLEAR removal from running."""
    schema = [
        _field(field_id=1, name="topic", filterable=True),  # cleared
        _field(field_id=2, name="year", field_type=FieldType.INTEGER, filterable=True),  # set
    ]
    filter_sync = SimpleNamespace(
        sync_document_filter_payloads=AsyncMock(side_effect=RuntimeError("down"))
    )
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "ai")))

    result = await facade.update_document_metadata(document.id, {"topic": None, "year": 2024})

    assert result.filter_repaint_failed is True
    assert mef.QdrantIndexApi.delete_payload.await_args.args[2] == ["topic"]


async def test_one_invalid_field_rejects_the_whole_patch_including_valid_clears(
    monkeypatch,
) -> None:
    """All-or-nothing: a valid clear alongside a bad SET writes and deletes NOTHING and touches no store."""
    schema = [
        _field(field_id=1, name="topic", filterable=True),
        _field(field_id=2, name="year", field_type=FieldType.INTEGER),
    ]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "ai")))

    with pytest.raises(MetadataValidationError) as excinfo:
        await facade.update_document_metadata(document.id, {"topic": None, "year": "nope"})

    assert len(excinfo.value.errors) == 1
    mef.DocumentApi.update_metadata.assert_not_awaited()
    mef.DocumentApi.delete_metadata.assert_not_awaited()
    mef.QdrantIndexApi.delete_payload.assert_not_awaited()
    mef.QdrantIndexApi.delete_vectors.assert_not_awaited()


async def test_validation_collects_every_error_in_one_raise(monkeypatch) -> None:
    """Unknown + chunk-scope + required-clear are all reported together, not first-error-only."""
    schema = [
        _field(field_id=1, name="sentiment", scope=FieldScope.CHUNK),
        _field(field_id=2, name="topic"),
    ]
    schema[1].required = True
    facade, document = _facade_with_schema(
        monkeypatch, schema, SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    )

    with pytest.raises(MetadataValidationError) as excinfo:
        await facade.update_document_metadata(
            document.id, {"ghost": "x", "sentiment": "pos", "topic": None}
        )

    joined = " | ".join(excinfo.value.errors)
    assert len(excinfo.value.errors) == 3
    assert "unknown field 'ghost'" in joined
    assert "chunk-scope" in joined
    assert "cannot be cleared" in joined


async def test_clearing_a_chunk_scope_field_is_rejected_not_cleared(monkeypatch) -> None:
    """null on a chunk-scope field hits the chunk-scope gate BEFORE the clear branch."""
    schema = [_field(field_id=1, name="sentiment", scope=FieldScope.CHUNK)]
    facade, document = _facade_with_schema(
        monkeypatch, schema, SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    )

    with pytest.raises(MetadataValidationError) as excinfo:
        await facade.update_document_metadata(document.id, {"sentiment": None})

    assert any("chunk-scope" in m for m in excinfo.value.errors)
    mef.DocumentApi.delete_metadata.assert_not_awaited()


async def test_nul_only_difference_is_not_a_change(monkeypatch) -> None:
    """A value differing from the stored one ONLY by a NUL strips to equal: no write, no repaint."""
    schema = [_field(field_id=1, name="topic", filterable=True)]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock())
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, "ai")))

    result = await facade.update_document_metadata(document.id, {"topic": "a" + chr(0) + "i"})

    assert result.updated_fields == []
    filter_sync.sync_document_filter_payloads.assert_not_awaited()
    assert mef.DocumentApi.update_metadata.await_args.args[2] == []


async def test_set_that_changes_a_value_overwrites_even_to_falsy(monkeypatch) -> None:
    """A falsy-but-non-null value (0) is a SET, not a clear, and counts as a change vs a stored 5."""
    schema = [_field(field_id=1, name="year", field_type=FieldType.INTEGER, filterable=True)]
    filter_sync = SimpleNamespace(sync_document_filter_payloads=AsyncMock(return_value=1))
    facade, document = _facade_with_schema(monkeypatch, schema, filter_sync)
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", _stored((1, 5)))

    result = await facade.update_document_metadata(document.id, {"year": 0})

    assert result.updated_fields == ["year"]
    mef.DocumentApi.delete_metadata.assert_awaited_once()
    assert mef.DocumentApi.delete_metadata.await_args.args[2] == []
    mef.QdrantIndexApi.delete_payload.assert_not_awaited()
