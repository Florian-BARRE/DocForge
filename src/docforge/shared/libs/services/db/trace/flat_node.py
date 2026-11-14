# ====== Code Summary ======
# FlatNode — one node of the execution tree resolved to its materialized-path coordinates (path,
# depth, parent path, fan-out item index). The row shape ExecutionTreeFlattener emits and the
# job_stage_event table stores. Pure: no DB, no engine state.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord


@dataclass(frozen=True, slots=True)
class FlatNode:
    """One node of the execution tree, resolved to its materialized-path coordinates.

    Attributes:
        record (NodeExecutionRecord): The node's execution record (status/kind/duration/error/usage/
            score are read from here at persist time).
        node_path (str): The node's materialized path (root = bare node id, nested = dotted path).
        depth (int): 0 for a root stage, +1 per nesting level.
        parent_path (str | None): The parent node's node_path (None for a root stage).
        item_index (int | None): The nearest enclosing ForEach item index (None outside any fan-out).
    """

    record: NodeExecutionRecord
    node_path: str
    depth: int
    parent_path: str | None
    item_index: int | None


__all__ = ["FlatNode"]
