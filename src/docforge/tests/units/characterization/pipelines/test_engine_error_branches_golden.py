# ====== Code Summary ======
# Characterization of FlowEngine's error / record-not-crash branches (safety net for the engine split):
# input-resolution failures (no binding, missing node, missing field, missing run input, off-type value),
# a cache hook that raises on lookup and on store, every ForEach failure (``over`` missing / not a list,
# a body violating the collection contract, a failing item, an item ending off-contract), a sub-group
# whose input cannot be resolved, the cycle guard, structural escapes, a resume at an unknown node and the
# run deadline. The golden captures the resulting RECORDS and MESSAGES (never a traceback) and the
# progress events, so a refactor that reorders, drops or re-types a branch fails here. The two branches
# that RAISE out of ``execute`` (a progress callback abort, the engine-invariant marker) are asserted
# explicitly below: their contract is the exception, not a record.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import AbstractNode, Group, NodeType
from shared_libs.pipelines.engine import EngineInvariantError, FlowEngine, ProgressEvent

# ====== Local Project Imports ======
from .support.engine_runner import EngineRunner
from .support.engine_scenarios import BRANCHES, foreach_group
from .support.golden_file import GoldenFile
from .support.record_projector import RecordProjector

GOLDEN = GoldenFile("engine_error_branches.json")


@pytest.mark.parametrize("name", list(BRANCHES))
def test_engine_error_branch_matches_its_golden(name: str) -> None:
    scenario = BRANCHES[name]()
    run = EngineRunner.run(
        scenario.group,
        scenario.run_input,
        trace_level=scenario.trace_level,
        cache_hook=scenario.cache_hook,
        resume=scenario.resume,
        timeout_seconds=scenario.timeout_seconds,
    )
    snapshot = {
        "output": run.output.model_dump(mode="json") if run.output is not None else None,
        "record": RecordProjector.record(run.record, scenario.with_summaries),
        "events": [RecordProjector.event(event) for event in run.events],
    }
    if scenario.cache_hook is not None:
        snapshot["cache_calls"] = scenario.cache_hook.calls
    GOLDEN.check(name, snapshot)


class _AbortError(Exception):
    """Stands for the worker's cooperative-cancel guard raising inside the progress callback."""


def _abort_at(phase: str, node_id: str, seen: list[tuple]) -> object:
    """A progress callback that logs each event, then raises ``_AbortError`` at ``(phase, node_id)``."""
    error = _AbortError(f"abort at {phase} of {node_id}")

    async def callback(event: ProgressEvent) -> None:
        seen.append(RecordProjector.event(event))
        if (event.phase.value, event.node_id) == (phase, node_id):
            raise error

    callback.error = error  # type: ignore[attr-defined]
    return callback


@pytest.mark.parametrize(
    ("phase", "node_id", "expected_seen"),
    [
        ("start", "src", [("start", "src", "charact_docs_producer", None, None)]),
        (
            "end",
            "src",
            [
                ("start", "src", "charact_docs_producer", None, None),
                ("end", "src", "charact_docs_producer", None, "success"),
            ],
        ),
        (
            "start",
            "each",
            [
                ("start", "src", "charact_docs_producer", None, None),
                ("end", "src", "charact_docs_producer", None, "success"),
                ("start", "each", "foreach", 2, None),
            ],
        ),
        (
            "start",
            "echo",
            [
                ("start", "src", "charact_docs_producer", None, None),
                ("end", "src", "charact_docs_producer", None, "success"),
                ("start", "each", "foreach", 2, None),
                ("start", "echo", "charact_item_echo", None, None),
            ],
        ),
    ],
    ids=["at_first_start", "at_first_end", "at_foreach_start", "inside_a_foreach_item"],  # the body
    # group of a ForEach emits no event of its own: only the nodes it contains do
)
def test_progress_callback_abort_reaches_the_caller_unchanged(
    phase: str, node_id: str, expected_seen: list[tuple]
) -> None:
    """An exception raised by the progress callback leaves ``execute`` UNCHANGED (the identical object),
    never as a recorded FAILED run — also from inside a concurrent ForEach item — and the events before
    the abort are exactly those listed."""
    seen: list[tuple] = []
    callback = _abort_at(phase, node_id, seen)
    with pytest.raises(_AbortError) as raised:
        asyncio.run(FlowEngine().execute(foreach_group(["a", "b"]), {}, progress_callback=callback))
    assert raised.value is callback.error  # type: ignore[attr-defined]
    assert seen[: len(expected_seen)] == expected_seen


def test_unsupported_node_type_raises_the_engine_invariant_marker() -> None:
    """A node that is neither action, foreach nor group escapes ``execute`` LOUDLY, never as a record."""

    class _Alien(AbstractNode):
        KIND = "charact_alien"
        NODE_TYPE = NodeType.ACTION
        NAME = "Alien"
        SUMMARY = "Not dispatchable."

        @classmethod
        def describe(cls):  # pragma: no cover - never described, only dispatched
            raise NotImplementedError

    with pytest.raises(EngineInvariantError, match="unsupported node type in group 'g': _Alien"):
        EngineRunner.run(Group(id="g", children=[_Alien(id="x")]))
