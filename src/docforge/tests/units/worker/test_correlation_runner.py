# ====== Code Summary ======
# Worker-side correlation binding: `with_correlation` binds the enqueued `correlation_id` kwarg into
# the shared ContextVar for the whole task (so the job's logs carry it), pops it so the wrapped task
# keeps its id-free signature, mints a fresh id when none is passed (cron jobs stay correlatable), and
# always releases the binding after the task. `functools.wraps` keeps the name arq registers it under.

# ====== Standard Library Imports ======
import re

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


async def test_binds_enqueued_id_for_the_task_duration() -> None:
    """The id passed as a task kwarg is readable off the ContextVar inside the task body."""
    from jobs.correlation import with_correlation  # noqa: PLC0415

    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    seen: dict[str, str | None] = {}

    async def _task(ctx: dict, doc_id: str) -> str:
        seen["cid"] = CorrelationContext.get()
        seen["doc"] = doc_id
        return "done"

    result = await with_correlation(_task)({}, "doc-1", correlation_id="job-cid-1")

    assert result == "done"
    assert seen["cid"] == "job-cid-1"
    assert seen["doc"] == "doc-1"  # the wrapped task never sees the popped correlation_id kwarg


async def test_mints_an_id_when_none_passed() -> None:
    """A cron-triggered job (no correlation_id kwarg) gets a freshly minted id — always correlatable."""
    from jobs.correlation import with_correlation  # noqa: PLC0415

    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    seen: dict[str, str | None] = {}

    async def _task(ctx: dict) -> None:
        seen["cid"] = CorrelationContext.get()

    await with_correlation(_task)({})

    assert _HEX32.match(seen["cid"])


async def test_binding_is_released_after_the_task() -> None:
    """The ContextVar is restored to unbound after the task returns (no bleed to the next job)."""
    from jobs.correlation import with_correlation  # noqa: PLC0415

    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    async def _task(ctx: dict) -> None:
        return None

    await with_correlation(_task)({}, correlation_id="ephemeral")

    assert CorrelationContext.get() is None


async def test_binding_is_released_even_on_task_error() -> None:
    """A failing task still releases the binding (finally), so the next job is not polluted."""
    from jobs.correlation import with_correlation  # noqa: PLC0415

    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    async def _task(ctx: dict) -> None:
        raise RuntimeError("boom")

    try:
        await with_correlation(_task)({}, correlation_id="ephemeral")
    except RuntimeError:
        pass

    assert CorrelationContext.get() is None


def test_wraps_preserves_name_for_arq_registration() -> None:
    """`functools.wraps` keeps __name__/__qualname__ so arq registers the task under its real name."""
    from jobs.correlation import with_correlation  # noqa: PLC0415

    async def ingest_document(ctx: dict) -> None:
        return None

    wrapped = with_correlation(ingest_document)
    assert wrapped.__name__ == "ingest_document"
    assert wrapped.__qualname__ == ingest_document.__qualname__
