"""QueueClient.enqueue_ingest against a REAL ``ArqRedis`` (backed by fakeredis, no network) — a
deeper regression lock than ``test_queue_enqueue.py``'s ``AsyncMock``-captured call. That file
asserts what OUR code passes to ``pool.enqueue_job``; this one runs the call through arq's actual
``enqueue_job`` (its WATCH/MULTI/EXEC pipeline + ``serialize_job``) and inspects what got written to
the wire, so it would also catch a future bug where a kwarg is spelled like a REAL control kwarg
(e.g. ``_job_ttl`` vs ``_expires``) but isn't one — a class of typo the pure-mock test can't see,
since arq itself (not our assertion) is what decides a kwarg is unknown and stuffs it into the task
args. Root cause of the shipped bug: ``_job_timeout`` is not one of arq's named control kwargs
(``_job_id``/``_queue_name``/``_defer_until``/``_defer_by``/``_expires``/``_job_try``), so it silently
fell into ``**kwargs`` and was serialized as a task argument — ``ingest_document(doc_id, job_id,
_job_timeout=30)`` then crashed at dispatch with an unexpected keyword argument.

fakeredis, not a real Redis: stays in the serviceless suite (no service, no network).
"""

import fakeredis
from arq.constants import job_key_prefix
from arq.jobs import deserialize_job_raw


async def _fake_pool():
    """A real ``ArqRedis`` wired onto an in-memory fakeredis backend."""
    from arq.connections import ArqRedis  # noqa: PLC0415

    fake = fakeredis.FakeAsyncRedis()
    return ArqRedis(connection_pool=fake.connection_pool), fake


async def _deserialize(fake, job_id: str) -> tuple[str, tuple, dict]:
    """Read back exactly what was written to the wire for one enqueued job."""
    raw = await fake.get(job_key_prefix + job_id)
    function, args, kwargs, _job_try, _enqueue_time_ms = deserialize_job_raw(raw)
    return function, args, kwargs


async def test_enqueue_ingest_wire_payload_has_no_stray_kwargs(fastapi_app) -> None:
    """The task dispatched to the worker carries ids-only args and ONLY the declared ``force`` kwarg.

    ``force`` is part of ingest_document's signature (a normal task kwarg, like correlation_id), so it
    is NOT a stray kwarg — the contract this guards is that no UNDECLARED / arq-control kwarg leaks
    onto the wire (which would be stuffed into the task args and crash the worker at dispatch)."""
    from backend.utils.queue import QueueClient  # noqa: PLC0415

    pool, fake = await _fake_pool()
    client = QueueClient("redis://localhost:6379")
    client._pool = pool
    try:
        await client.enqueue_ingest("doc-1", "job-1")

        (job_id,) = [key async for key in fake.scan_iter(job_key_prefix + "*")]
        function, args, kwargs = await _deserialize(
            fake, job_id.decode().removeprefix(job_key_prefix)
        )

        assert function == "ingest_document"
        assert args == ("doc-1", "job-1")
        # Only the declared ``force`` flag rides; no _-prefixed arq control kwarg leaked.
        assert kwargs == {"force": False}, f"stray kwarg reached the wire: {kwargs}"
        assert not any(key.startswith("_") for key in kwargs)
    finally:
        await fake.aclose()


async def test_a_stray_control_looking_kwarg_would_be_caught_by_this_contract(fastapi_app) -> None:
    """Sanity check the contract test itself: reproduce the shipped bug shape directly against arq
    (bypassing QueueClient) to prove ``_job_timeout`` really does leak into the task kwargs — i.e.
    the assertion above is not vacuously true."""
    pool, fake = await _fake_pool()
    try:
        job = await pool.enqueue_job("ingest_document", "doc-2", "job-2", _job_timeout=30)
        assert job is not None
        _function, _args, kwargs = await _deserialize(fake, job.job_id)
        assert kwargs == {"_job_timeout": 30}  # confirms arq does NOT recognise it as control
    finally:
        await fake.aclose()
