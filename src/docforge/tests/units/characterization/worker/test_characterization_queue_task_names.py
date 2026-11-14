# ====== Code Summary ======
# CHARACTERIZATION of the app <-> worker task-name contract: ``QueueClient`` enqueues tasks BY STRING
# NAME, the worker registers them by function name, and arq silently drops a job whose name is not
# registered. This pins (1) the task names every ``QueueClient.enqueue_*`` method really puts on the wire
# (a real ``ArqRedis`` over fakeredis — no network), (2) the names the worker's ``WorkerSettings`` registers
# (normalised the way arq's own Worker does), and (3) that both sets are EQUAL. A typo on either side, or a
# new enqueue method without its worker function, fails here instead of dropping jobs in production.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
import fakeredis
import pytest
from arq.connections import ArqRedis
from arq.constants import job_key_prefix
from arq.jobs import deserialize_job_raw
from arq.worker import func
from characterization_worker_app_loader import WorkerAppLoader

# The golden: which task name(s) each public enqueue method puts on the queue.
_TASKS_BY_ENQUEUE_METHOD = {
    "enqueue_backfill": ["backfill_collection_filters", "backfill_collection_meta_vectors"],
    "enqueue_document_metadata_sync": ["sync_document_metadata"],
    "enqueue_export": ["export_collection"],
    "enqueue_import": ["import_collection"],
    "enqueue_ingest": ["ingest_document"],
    "enqueue_preview": ["preview_pipeline"],
    "enqueue_rebuild_index": ["rebuild_collection_index"],
}

_REGISTERED_TASKS_IN_ORDER = [
    "ingest_document",
    "backfill_collection_filters",
    "backfill_collection_meta_vectors",
    "sync_document_metadata",
    "rebuild_collection_index",
    "export_collection",
    "import_collection",
    "preview_pipeline",
]

# How to call each enqueue method (the arguments are ids/scalars only, as the routers pass them).
_CALLS = {
    "enqueue_backfill": lambda client: client.enqueue_backfill("collection-1"),
    "enqueue_document_metadata_sync": lambda client: client.enqueue_document_metadata_sync(
        "doc-1", "job-1"
    ),
    "enqueue_export": lambda client: client.enqueue_export("collection-1", "transfer-1"),
    "enqueue_import": lambda client: client.enqueue_import("bundle.zip", "transfer-1", None, None),
    "enqueue_ingest": lambda client: client.enqueue_ingest("doc-1", "job-1"),
    "enqueue_preview": lambda client: client.enqueue_preview(
        uuid.uuid4().hex, "collection-1", None, b"x", {}, "f.pdf", None, None
    ),
    "enqueue_rebuild_index": lambda client: client.enqueue_rebuild_index("collection-1", "job-1"),
}


@pytest.fixture(scope="module")
def queue_client_class():
    return WorkerAppLoader.load_queue_client()


async def _task_names_enqueued_by(queue_client_class, method_name: str) -> list[str]:
    """Run one enqueue method against a fresh fakeredis-backed ArqRedis; return the wire task names."""
    fake = fakeredis.FakeAsyncRedis()
    client = queue_client_class("redis://localhost:6379")
    client._pool = ArqRedis(connection_pool=fake.connection_pool)
    try:
        await _CALLS[method_name](client)
        names = []
        async for key in fake.scan_iter(job_key_prefix + "*"):
            function, _args, _kwargs, _try, _enqueue_ms = deserialize_job_raw(await fake.get(key))
            names.append(function)
        return sorted(names)
    finally:
        await fake.aclose()


def _registered_task_names(load_worker_app) -> list[str]:
    """The names arq's Worker registers for WorkerSettings.functions (``func(f).name``, in order)."""
    settings = load_worker_app().create_worker_settings()
    return [func(function).name for function in settings.functions]


def test_every_public_enqueue_method_is_covered_by_the_golden(queue_client_class) -> None:
    """A NEW ``enqueue_*`` method must be added to the golden (and to the worker) on purpose."""
    methods = sorted(name for name in dir(queue_client_class) if name.startswith("enqueue_"))

    assert methods == sorted(_TASKS_BY_ENQUEUE_METHOD)


@pytest.mark.parametrize("method_name", sorted(_TASKS_BY_ENQUEUE_METHOD))
async def test_each_enqueue_method_puts_exactly_its_task_names_on_the_wire(
    queue_client_class, method_name
) -> None:
    names = await _task_names_enqueued_by(queue_client_class, method_name)

    assert names == sorted(_TASKS_BY_ENQUEUE_METHOD[method_name])


def test_the_worker_registers_exactly_the_eight_task_functions_in_this_order(
    load_worker_app,
) -> None:
    assert _registered_task_names(load_worker_app) == _REGISTERED_TASKS_IN_ORDER


def test_the_preview_task_keeps_its_result_in_redis_for_the_configured_ttl(load_worker_app) -> None:
    settings = load_worker_app().create_worker_settings()

    keep_results = {
        func(function).name: func(function).keep_result_s for function in settings.functions
    }

    assert keep_results["preview_pipeline"] == 1800.0
    assert [name for name, ttl in keep_results.items() if ttl is not None] == ["preview_pipeline"]


async def test_the_task_names_the_app_can_enqueue_equal_the_task_names_the_worker_registers(
    queue_client_class, load_worker_app
) -> None:
    """The parity guard: a name enqueued but not registered would be dropped silently by arq."""
    enqueued: set[str] = set()
    for method_name in _CALLS:
        enqueued.update(await _task_names_enqueued_by(queue_client_class, method_name))

    registered = set(_registered_task_names(load_worker_app))

    assert enqueued == registered
    assert len(registered) == 8


def test_no_registered_task_name_is_duplicated(load_worker_app) -> None:
    names = _registered_task_names(load_worker_app)

    assert len(names) == len(set(names))
