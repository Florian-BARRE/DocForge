"""Collection PATCH schema ops (wave E1 / finding D1): ``field_ops`` + ``dry_run`` + ``schema_diff``.

Pins the pure planner/differ (add/update/remove/rename, rename collapse, validation errors,
values_lost, reindex fields) and the route contract (fields+field_ops → 422, dry_run writes nothing,
renames reach the facade spec, departed fields are purged post-commit). Stores are mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.services.db.facades import CollectionUpdateResult

FAKE_ID = "33333333-3333-3333-3333-333333333333"


def _spec(name: str, **flags):
    from backend.libs.schema_ops import FieldSpecModel  # noqa: PLC0415

    return FieldSpecModel(field_name=name, field_type="string", **flags)


def _ops(*raw: dict):
    from pydantic import TypeAdapter  # noqa: PLC0415

    from backend.libs.schema_ops import FieldOp  # noqa: PLC0415

    return TypeAdapter(list[FieldOp]).validate_python(list(raw))


# -------------------- planner --------------------
def test_planner_applies_every_op_kind() -> None:
    from backend.libs.schema_ops import SchemaOpsPlanner  # noqa: PLC0415

    current = [_spec("author"), _spec("region"), _spec("old")]
    plan = SchemaOpsPlanner.from_ops(
        current,
        _ops(
            {"op": "add", "field": {"field_name": "year", "field_type": "integer"}},
            {"op": "update", "field_name": "region", "changes": {"filterable": True}},
            {"op": "remove", "field_name": "old"},
            {"op": "rename", "field_name": "author", "new_name": "writer"},
        ),
    )
    assert [s.field_name for s in plan.target] == ["region", "year", "writer"]
    assert plan.renames == {"author": "writer"}
    assert plan.removed == ["old"]
    assert next(s for s in plan.target if s.field_name == "region").filterable is True


def test_planner_collapses_a_rename_chain() -> None:
    from backend.libs.schema_ops import SchemaOpsPlanner  # noqa: PLC0415

    plan = SchemaOpsPlanner.from_ops(
        [_spec("a")],
        _ops(
            {"op": "rename", "field_name": "a", "new_name": "b"},
            {"op": "rename", "field_name": "b", "new_name": "c"},
        ),
    )
    assert plan.renames == {"a": "c"} and plan.removed == []


@pytest.mark.parametrize(
    "ops",
    [
        [{"op": "remove", "field_name": "ghost"}],
        [{"op": "update", "field_name": "ghost", "changes": {"filterable": True}}],
        [{"op": "rename", "field_name": "ghost", "new_name": "x"}],
        [{"op": "add", "field": {"field_name": "a", "field_type": "string"}}],
        [{"op": "rename", "field_name": "a", "new_name": "b"}],
        [
            {"op": "remove", "field_name": "a"},
            {"op": "add", "field": {"field_name": "a", "field_type": "string"}},
        ],
        [{"op": "update", "field_name": "a", "changes": {"field_type": None}}],
    ],
)
def test_planner_rejects_invalid_ops(ops) -> None:
    from backend.libs.schema_ops import SchemaOpsError, SchemaOpsPlanner  # noqa: PLC0415

    with pytest.raises(SchemaOpsError):
        SchemaOpsPlanner.from_ops([_spec("a"), _spec("b")], _ops(*ops))


def test_legacy_fields_plan_reports_omitted_fields_as_removed() -> None:
    from backend.libs.schema_ops import SchemaOpsPlanner  # noqa: PLC0415

    plan = SchemaOpsPlanner.from_fields([_spec("a"), _spec("b")], [_spec("a")])
    assert plan.removed == ["b"] and plan.renames == {}


# -------------------- differ --------------------
def test_differ_reports_every_bucket_and_values_lost() -> None:
    from backend.libs.schema_ops import SchemaDiffer, SchemaOpsPlanner  # noqa: PLC0415

    current = [_spec("author", semantic=True), _spec("region"), _spec("old")]
    plan = SchemaOpsPlanner.from_ops(
        current,
        _ops(
            {"op": "add", "field": {"field_name": "year", "field_type": "string", "lexical": True}},
            {"op": "update", "field_name": "region", "changes": {"semantic": True}},
            {"op": "remove", "field_name": "old"},
            {"op": "rename", "field_name": "author", "new_name": "writer"},
        ),
    )
    diff = SchemaDiffer.build(current, plan, {"old": 7}, indexed=True)
    assert diff.added == ["year"]
    assert [(m.field_name, m.changed_attrs) for m in diff.modified] == [("region", ["semantic"])]
    assert diff.removed == ["old"] and diff.values_lost == {"old": 7}
    assert [(r.from_name, r.to_name) for r in diff.renamed] == [("author", "writer")]
    assert sorted(diff.reindex_required_fields) == ["region", "writer", "year"]


def test_differ_never_requires_reindex_on_a_never_indexed_collection() -> None:
    from backend.libs.schema_ops import SchemaDiffer, SchemaOpsPlanner  # noqa: PLC0415

    plan = SchemaOpsPlanner.from_fields([], [_spec("a", semantic=True)])
    assert SchemaDiffer.build([], plan, {}, indexed=False).reindex_required_fields == []


def test_differ_rename_then_add_same_name_reports_an_add() -> None:
    """M3: rename A→B then add a NEW A — the new A has no stored origin (the stored A is now B)."""
    from backend.libs.schema_ops import SchemaDiffer, SchemaOpsPlanner  # noqa: PLC0415

    current = [_spec("a", filterable=True)]
    plan = SchemaOpsPlanner.from_ops(
        current,
        _ops(
            {"op": "rename", "field_name": "a", "new_name": "b"},
            {"op": "add", "field": {"field_name": "a", "field_type": "string", "semantic": True}},
        ),
    )
    diff = SchemaDiffer.build(current, plan, {}, indexed=True)
    assert diff.added == ["a"] and diff.modified == []
    assert [(r.from_name, r.to_name) for r in diff.renamed] == [("a", "b")]
    assert "a" in diff.reindex_required_fields


def test_differ_swap_is_two_renames_no_add() -> None:
    from backend.libs.schema_ops import SchemaDiffer, SchemaOpsPlanner  # noqa: PLC0415

    current = [_spec("a", semantic=True), _spec("b", filterable=True)]
    plan = SchemaOpsPlanner.from_ops(
        current,
        _ops(
            {"op": "rename", "field_name": "a", "new_name": "tmp"},
            {"op": "rename", "field_name": "b", "new_name": "a"},
            {"op": "rename", "field_name": "tmp", "new_name": "b"},
        ),
    )
    diff = SchemaDiffer.build(current, plan, {}, indexed=True)
    assert plan.renames == {"a": "b", "b": "a"}
    assert diff.added == [] and diff.modified == [] and diff.removed == []
    # The semantic field now lives under "b" (renamed → its vectors move): reindex it, not "a".
    assert diff.reindex_required_fields == ["b"]


def test_differ_rename_chain_is_one_rename() -> None:
    from backend.libs.schema_ops import SchemaDiffer, SchemaOpsPlanner  # noqa: PLC0415

    current = [_spec("a")]
    plan = SchemaOpsPlanner.from_ops(
        current,
        _ops(
            {"op": "rename", "field_name": "a", "new_name": "b"},
            {"op": "rename", "field_name": "b", "new_name": "c"},
        ),
    )
    diff = SchemaDiffer.build(current, plan, {}, indexed=True)
    assert diff.added == [] and diff.modified == []
    assert [(r.from_name, r.to_name) for r in diff.renamed] == [("a", "c")]


# -------------------- departed (M4: never purge a live name) --------------------
def _departed(current, *ops) -> list[str]:
    from backend.libs.schema_ops import SchemaOpsPlanner  # noqa: PLC0415
    from backend.routers.collections.schema_patch import ResolvedSchemaPatch  # noqa: PLC0415

    plan = SchemaOpsPlanner.from_ops(current, _ops(*ops))
    return ResolvedSchemaPatch(plan=plan, rows=[], diff=None).departed


def test_departed_swap_purges_nothing() -> None:
    assert (
        _departed(
            [_spec("a"), _spec("b")],
            {"op": "rename", "field_name": "a", "new_name": "tmp"},
            {"op": "rename", "field_name": "b", "new_name": "a"},
            {"op": "rename", "field_name": "tmp", "new_name": "b"},
        )
        == []
    )


def test_departed_remove_then_rename_into_purges_only_the_old_name() -> None:
    assert _departed(
        [_spec("a"), _spec("b")],
        {"op": "remove", "field_name": "a"},
        {"op": "rename", "field_name": "b", "new_name": "a"},
    ) == ["b"]


def test_departed_plain_rename_purges_the_old_name() -> None:
    assert _departed([_spec("a")], {"op": "rename", "field_name": "a", "new_name": "b"}) == ["a"]


# -------------------- route --------------------
def _row(name: str):
    from shared_libs.services.db.postgresql.tables import MetadataField  # noqa: PLC0415

    return MetadataField(
        field_name=name,
        field_type="string",
        required=False,
        filterable=True,
        lexical=False,
        semantic=False,
        origin="user",
        scope="document",
    )


def _mock(monkeypatch, *, values: dict[str, int] | None = None):
    from backend.context import CONTEXT  # noqa: PLC0415

    fake = SimpleNamespace(
        id=uuid.UUID(FAKE_ID),
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
        indexed_signature="sig",
    )
    collections = SimpleNamespace(
        get=AsyncMock(return_value=fake),
        get_by_name=AsyncMock(return_value=None),
        get_schema=AsyncMock(return_value=[_row("author"), _row("old")]),
        apply_update=AsyncMock(
            return_value=CollectionUpdateResult(schema_applied=True, schema_reindex_required=False)
        ),
        reconcile_store=AsyncMock(return_value=set()),
    )
    schema_changes = SimpleNamespace(
        count_field_values=AsyncMock(return_value=values or {}),
        purge_departed_fields=AsyncMock(),
    )
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=collections,
            schema_changes=schema_changes,
            index_state=SimpleNamespace(
                missing=AsyncMock(return_value=[]), missing_for=AsyncMock(return_value=[])
            ),
        ),
    )
    queue = SimpleNamespace(enqueue_backfill=AsyncMock())
    monkeypatch.setattr(CONTEXT, "queue", queue, raising=False)
    return collections, schema_changes, queue


def test_fields_and_field_ops_together_is_a_422(client, monkeypatch) -> None:
    collections, _, _ = _mock(monkeypatch)
    body = {
        "fields": [{"field_name": "a", "field_type": "string"}],
        "field_ops": [{"op": "remove", "field_name": "old"}],
    }
    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json=body)
    assert response.status_code == 422
    collections.apply_update.assert_not_awaited()


def test_unknown_field_op_target_is_a_422(client, monkeypatch) -> None:
    collections, _, _ = _mock(monkeypatch)
    body = {"field_ops": [{"op": "remove", "field_name": "ghost"}]}
    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json=body)
    assert response.status_code == 422 and "ghost" in response.text
    collections.apply_update.assert_not_awaited()


def test_dry_run_returns_the_diff_and_writes_nothing(client, monkeypatch) -> None:
    collections, schema_changes, queue = _mock(monkeypatch, values={"old": 12})
    body = {"field_ops": [{"op": "remove", "field_name": "old"}], "dry_run": True}
    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["schema_diff"]["removed"] == ["old"]
    assert payload["schema_diff"]["values_lost"] == {"old": 12}
    assert [f["field_name"] for f in payload["fields"]] == ["author", "old"]  # unchanged
    collections.apply_update.assert_not_awaited()
    collections.reconcile_store.assert_not_awaited()
    schema_changes.purge_departed_fields.assert_not_awaited()
    queue.enqueue_backfill.assert_not_awaited()


def test_rename_reaches_the_facade_and_departed_names_are_purged(client, monkeypatch) -> None:
    collections, schema_changes, _ = _mock(monkeypatch)
    body = {
        "field_ops": [
            {"op": "rename", "field_name": "author", "new_name": "writer"},
            {"op": "remove", "field_name": "old"},
        ]
    }
    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json=body)
    assert response.status_code == 200, response.text
    spec = collections.apply_update.await_args.args[1]
    assert spec.schema_renames == {"author": "writer"}
    assert [row.field_name for row in spec.schema_fields] == ["writer"]
    diff = response.json()["schema_diff"]
    assert diff["renamed"] == [{"from_name": "author", "to_name": "writer"}]
    assert response.json()["dry_run"] is False
    schema_changes.purge_departed_fields.assert_awaited_once_with(
        uuid.UUID(FAKE_ID), ["old", "author"]
    )


def test_legacy_fields_report_removed_fields(client, monkeypatch) -> None:
    _mock(monkeypatch, values={"old": 3})
    body = {"fields": [{"field_name": "author", "field_type": "string", "filterable": True}]}
    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["schema_diff"]["removed"] == ["old"]
    assert response.json()["schema_diff"]["values_lost"] == {"old": 3}


def test_store_purge_failure_never_fails_the_patch(client, monkeypatch) -> None:
    _, schema_changes, queue = _mock(monkeypatch)
    schema_changes.purge_departed_fields.side_effect = RuntimeError("qdrant down")
    body = {"field_ops": [{"op": "remove", "field_name": "old"}]}
    assert client.patch(f"/api/v1/collections/{FAKE_ID}", json=body).status_code == 200
    queue.enqueue_backfill.assert_awaited_once()


def test_non_schema_patch_carries_an_empty_diff(client, monkeypatch) -> None:
    _mock(monkeypatch)
    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json={"name": "c2"})
    assert response.status_code == 200, response.text
    assert response.json()["schema_diff"]["removed"] == []
