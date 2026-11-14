# ====== Code Summary ======
# Unit tests of the data layer's shared bricks (R-02): VectorSpaceProvisioner projects the schema onto
# the semantic / lexical / filterable field families exactly as the three former copies did, and the
# two BlobApi stage-artifact queries keep the SQL the artifact-cache facade used to issue inline.
# ConstraintViolation itself is pinned by characterization/services/test_constraint_decoder.py.

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy.dialects import postgresql

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType
from shared_libs.services.db.bricks import VectorSpaceProvisioner
from shared_libs.services.db.bricks import vector_space_provisioner as provisioner_module
from shared_libs.services.db.postgresql.apis import BlobApi
from shared_libs.services.db.qdrant import PayloadType


def _sql(statement) -> str:
    """The statement compiled for PostgreSQL, one trimmed line per compiler line."""
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    return "\n".join(line.strip() for line in compiled.strip().splitlines())


def _field(name: str, field_type: FieldType, **flags: bool) -> SimpleNamespace:
    return SimpleNamespace(
        field_name=name,
        field_type=field_type,
        semantic=flags.get("semantic", False),
        lexical=flags.get("lexical", False),
        filterable=flags.get("filterable", False),
    )


@pytest.mark.asyncio
async def test_provisioner_projects_the_schema_onto_the_three_field_families(monkeypatch) -> None:
    ensure = AsyncMock(return_value={"title"})
    monkeypatch.setattr(provisioner_module.QdrantCollectionApi, "ensure", ensure)
    schema = [
        _field("title", FieldType.STRING, semantic=True, lexical=True, filterable=True),
        _field("year", FieldType.INTEGER, filterable=True),
        _field("notes", FieldType.TEXT),
    ]
    client, layout = MagicMock(), MagicMock()

    missing = await VectorSpaceProvisioner.ensure(client, "col_x", schema, 1024, layout)

    assert missing == {"title"}
    ensure.assert_awaited_once_with(
        client,
        "col_x",
        dense_dim=1024,
        semantic_fields=["title"],
        lexical_fields=["title"],
        filterable_fields={"title": PayloadType.KEYWORD, "year": PayloadType.INTEGER},
        layout=layout,
    )


@pytest.mark.asyncio
async def test_orphan_stage_artifacts_sql_with_and_without_grace() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.execute.return_value.scalars.return_value.all.return_value = ["h1"]

    assert await BlobApi.orphan_stage_artifacts(session, None) == ["h1"]
    plain = _sql(session.execute.await_args.args[0])
    await BlobApi.orphan_stage_artifacts(session, datetime(2026, 1, 1, tzinfo=UTC))
    aged = _sql(session.execute.await_args.args[0])

    assert "blob.kind =" in plain
    assert "blob.content_hash NOT IN (SELECT artifact_cache.content_hash" in plain
    assert "created_at <" not in plain
    assert "blob.created_at <" in aged


@pytest.mark.asyncio
async def test_delete_stage_artifacts_only_deletes_stage_artifact_rows() -> None:
    session = MagicMock()
    session.execute = AsyncMock()

    await BlobApi.delete_stage_artifacts(session, ["h1", "h2"])

    sql = _sql(session.execute.await_args.args[0])
    assert sql.startswith("DELETE FROM blob")
    assert "blob.content_hash IN" in sql
    assert "blob.kind =" in sql
