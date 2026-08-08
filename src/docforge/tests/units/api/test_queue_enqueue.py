"""QueueClient.enqueue_ingest — the per-collection job budget is threaded to arq as the control
kwarg ``_job_timeout`` (budget + 60, so arq's outer cap sits ABOVE the engine's clean timeout),
and is OMITTED entirely when the collection inherits the global default (None) so arq falls back
to its WorkerSettings default. The queued message itself stays IDS ONLY — the budget is never a
task arg. The lazy arq pool is faked, so no Redis is touched.
"""

from unittest.mock import AsyncMock


def _queue_with_fake_pool(fastapi_app) -> tuple:
    """A QueueClient whose lazy pool is pre-seeded with an AsyncMock, so enqueue_job is captured.

    Depends on ``fastapi_app`` only to guarantee the APP's ``backend`` package is the one on
    sys.path (the worker suite can otherwise register a competing ``backend`` — see worker conftest).
    """
    from backend.utils.queue import (
        QueueClient,  # noqa: PLC0415 — deferred until app/ is on sys.path
    )

    client = QueueClient("redis://localhost:6379")
    pool = AsyncMock()
    client._pool = pool  # skip the lazy create_pool — the pool is a mock
    return client, pool


async def test_enqueue_ingest_passes_job_timeout_when_budget_set(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_ingest("doc-1", "job-1", 120.0)

    # Positional args stay IDS ONLY; the budget rides as arq's _job_timeout = budget + 60.
    pool.enqueue_job.assert_awaited_once_with(
        "ingest_document", "doc-1", "job-1", _job_timeout=180.0
    )


async def test_enqueue_ingest_omits_job_timeout_when_budget_none(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_ingest("doc-1", "job-1", None)

    # No override → arq uses its WorkerSettings default; _job_timeout must not be passed at all.
    pool.enqueue_job.assert_awaited_once_with("ingest_document", "doc-1", "job-1")


async def test_enqueue_ingest_defaults_to_no_budget(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_ingest("doc-1", "job-1")

    pool.enqueue_job.assert_awaited_once_with("ingest_document", "doc-1", "job-1")
