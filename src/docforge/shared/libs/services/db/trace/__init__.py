# ====== Code Summary ======
# Pure execution-tree / trace code, kept apart from the SQL layer: ExecutionTreeFlattener turns the
# engine's NodeExecutionRecord tree into FlatNode rows (materialized paths), TraceRefs carries the
# object-store keys of a node's full payloads. No DB, no object-store I/O; import from this facade.

from .execution_tree_flattener import ExecutionTreeFlattener
from .flat_node import FlatNode
from .trace_refs import TraceRefs

__all__ = ["ExecutionTreeFlattener", "FlatNode", "TraceRefs"]
