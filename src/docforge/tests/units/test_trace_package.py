"""services/db/trace — the pure execution-tree code lives there; the old apis paths re-export it (R-10)."""

from shared_libs.services.db import trace
from shared_libs.services.db.postgresql import apis
from shared_libs.services.db.postgresql.apis import execution_tree as legacy_execution_tree


def test_trace_package_exposes_the_pure_trace_classes():
    assert {"ExecutionTreeFlattener", "FlatNode", "TraceRefs"} <= set(trace.__all__)
    assert trace.ExecutionTreeFlattener.__module__.startswith("shared_libs.services.db.trace.")
    assert trace.TraceRefs.__module__.startswith("shared_libs.services.db.trace.")


def test_legacy_apis_paths_reexport_the_same_objects():
    assert legacy_execution_tree.ExecutionTreeFlattener is trace.ExecutionTreeFlattener
    assert legacy_execution_tree.FlatNode is trace.FlatNode
    assert legacy_execution_tree.TraceRefs is trace.TraceRefs
    assert apis.ExecutionTreeFlattener is trace.ExecutionTreeFlattener
    assert apis.FlatNode is trace.FlatNode
