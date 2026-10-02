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


def _facade_with_schema(monkeypatch, schema: list[SimpleNamespace], filter_sync: MagicMock):
    """Build a MetadataEditFacade whose DB reads resolve to ``schema`` and a stub filter-sync."""
    document = MagicMock(id=uuid.uuid4(), collection_id=uuid.uuid4())
    monkeypatch.setattr(mef.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(mef.CollectionApi, "get_schema", AsyncMock(return_value=schema))
    monkeypatch.setattr(mef.DocumentApi, "update_metadata", AsyncMock())
    # Default: nothing stored yet → every requested field reads as changed. Tests that exercise the
    # no-op/change-detection path re-stub get_metadata with the stored rows they want to compare to.
    monkeypatch.setattr(mef.DocumentApi, "get_metadata", AsyncMock(return_value=[]))
    facade = MetadataEditFacade(_postgres_yielding(MagicMock()), filter_sync)
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
    )

    with pytest.raises(MetadataEditNotFoundError):
        await facade.update_document_metadata(uuid.uuid4(), {"topic": "ai"})
