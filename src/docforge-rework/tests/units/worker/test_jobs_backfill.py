"""backfill_collection_filters / backfill_collection_meta_vectors — the arq maintenance tasks: the
string collection_id (arq's queue carries strings) is coerced to uuid.UUID before hitting the
facade, and the facade's (documents, points) tuple is reshaped into the task's dict contract."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _fake_context(filters_result=(3, 7), meta_vectors_result=(2, 5)) -> SimpleNamespace:
    return SimpleNamespace(
        database=SimpleNamespace(
            filters=SimpleNamespace(
                backfill_collection_filter_payloads=AsyncMock(return_value=filters_result)
            ),
            meta_vectors=SimpleNamespace(
                backfill_collection_meta_vectors=AsyncMock(return_value=meta_vectors_result)
            ),
        ),
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )


async def test_backfill_collection_filters_coerces_uuid_and_shapes_result(
    jobs_backfill, monkeypatch
) -> None:
    context = _fake_context(filters_result=(3, 7))
    monkeypatch.setattr(jobs_backfill, "CONTEXT", context)
    collection_id = uuid.uuid4()

    result = await jobs_backfill.backfill_collection_filters({}, str(collection_id))

    assert result == {"documents": 3, "points": 7}
    args = context.database.filters.backfill_collection_filter_payloads.await_args.args
    assert args[0] == collection_id
    assert isinstance(args[0], uuid.UUID)


async def test_backfill_collection_meta_vectors_coerces_uuid_and_shapes_result(
    jobs_backfill, monkeypatch
) -> None:
    context = _fake_context(meta_vectors_result=(2, 5))
    monkeypatch.setattr(jobs_backfill, "CONTEXT", context)
    collection_id = uuid.uuid4()

    result = await jobs_backfill.backfill_collection_meta_vectors({}, str(collection_id))

    assert result == {"documents": 2, "points": 5}
    args = context.database.meta_vectors.backfill_collection_meta_vectors.await_args.args
    assert args[0] == collection_id
    assert isinstance(args[0], uuid.UUID)
