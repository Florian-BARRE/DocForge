# ====== Code Summary ======
# Characterization of FlowEngine's normal runs (safety net for splitting engine/core.py into FlowEngine /
# ActionRunner / ForEachRunner). Each scenario is a small fixed graph of fake nodes; the golden records
# today's observable behaviour: the final output, the NodeExecutionRecord tree (node id, kind, status,
# score, nesting — and the summary shapes where the scenario asks) and the ordered progress events.
# Durations and tracebacks are the only things left out. A drifted golden is a refactoring decision to
# review (see support/golden_file.py), never a test to fix.

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from .support.engine_runner import EngineRunner
from .support.engine_scenarios import HAPPY
from .support.golden_file import GoldenFile
from .support.record_projector import RecordProjector

GOLDEN = GoldenFile("engine_happy_path.json")


@pytest.mark.parametrize("name", list(HAPPY))
def test_engine_run_matches_its_golden(name: str) -> None:
    scenario = HAPPY[name]()
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
