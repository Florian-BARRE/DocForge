"""QueueClient.enqueue_ingest — the queued message is IDS ONLY. arq has no per-message job timeout
(``enqueue_job`` accepts only ``_job_id``/``_queue_name``/``_defer_*``/``_expires``), so a budget is
NEVER passed to it — passing an unknown ``_job_timeout`` kwarg would land as a task arg and crash
``ingest_document``. The per-collection budget is applied by the WORKER (it reads
``collection.job_timeout_seconds`` and hands it to the engine). The lazy arq pool is faked, so no
Redis is touched.
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


async def test_enqueue_ingest_message_is_ids_only(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_ingest("doc-1", "job-1")

    # IDS ONLY plus the ``force`` task flag (a NORMAL task kwarg ingest_document declares, NOT an arq
    # control kwarg): no _job_timeout or any other _-prefixed control kwarg — arq has no per-message
    # timeout, and an unknown control kwarg would be serialized as a task arg and blow up dispatch.
    pool.enqueue_job.assert_awaited_once_with("ingest_document", "doc-1", "job-1", force=False)


async def test_enqueue_ingest_never_passes_a_timeout_kwarg(fastapi_app) -> None:
    client, pool = _queue_with_fake_pool(fastapi_app)

    await client.enqueue_ingest("doc-1", "job-1")

    _, kwargs = pool.enqueue_job.await_args
    # Only ``force`` (a declared task kwarg) rides — never an arq CONTROL kwarg like _job_timeout.
    assert kwargs == {"force": False}, "enqueue_ingest must pass no arq control kwargs"
    assert not any(key.startswith("_") for key in kwargs), "no reserved arq control kwarg"
