# ====== Code Summary ======
# ExecutionTreeFlattener — turns the engine's recursive NodeExecutionRecord tree into a flat list of
# materialized-path rows the job_stage_event table stores. Every node (nested group children and
# per-item ForEach body instances included) becomes one FlatNode carrying its computed node_path,
# depth, parent_path and fan-out item_index — so the read side can rebuild the whole tree from the
# path string alone. Pure: no DB, no engine state, just a depth-first walk over the record.

# ====== Standard Library Imports ======
import re
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord

# A ForEach stamps each item's body record node_id as ``<body_id>[<index>]`` — the fan-out item marker.
_ITEM_INDEX_RE = re.compile(r"\[(\d+)\]$")


@dataclass(frozen=True, slots=True)
class TraceRefs:
    """The object-store references to a node's FULL input/output payloads (the full trace tier).

    Produced by the worker's payload-store step (content-hash keys) and consumed by
    ``persist_execution_tree`` to stamp ``input_ref``/``output_ref`` + the ``has_full_*`` flags on the
    node's row. A side left None means that payload was not stored (not captured, or a store miss).

    Attributes:
        input_ref (str | None): Object-store key of the node's full input payload, or None.
        output_ref (str | None): Object-store key of the node's full output payload, or None.
    """

    input_ref: str | None = None
    output_ref: str | None = None


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


class ExecutionTreeFlattener:
    """Static helper: flatten an execution record tree into materialized-path rows."""

    logger = loggerplusplus.bind(identifier="ExecutionTreeFlattener")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ExecutionTreeFlattener is a static-only class and cannot be instantiated.")

    @classmethod
    def flatten(cls, root_group: NodeExecutionRecord) -> list[FlatNode]:
        """
        Flatten the OUTERMOST group record's children into materialized-path rows.

        The outermost group record is the pipeline itself — the live recorder never opens a stage
        row for it, so it is skipped and its direct children become the depth-0 root stages (the
        rows the recorder already opened). Every descendant is emitted in depth-first, parent-before-
        child order.

        Args:
            root_group (NodeExecutionRecord): The pipeline's top-level execution record.

        Returns:
            list[FlatNode]: One entry per node in the tree, roots first, each child after its parent.
        """
        flat: list[FlatNode] = []
        for child in root_group.children:
            cls._walk(child, parent_path=None, depth=0, inherited_item=None, out=flat)
        return flat

    @classmethod
    def _walk(
        cls,
        record: NodeExecutionRecord,
        parent_path: str | None,
        depth: int,
        inherited_item: int | None,
        out: list[FlatNode],
    ) -> None:
        """Recurse one record into the flat list (depth-first, parent before its children)."""
        # 1. This node's own fan-out index: a ForEach body item's node_id encodes ``[<index>]``;
        #    otherwise inherit the nearest enclosing foreach frame's index (like FailureBreadcrumb).
        match = _ITEM_INDEX_RE.search(record.node_id)
        item_index = int(match.group(1)) if match else inherited_item

        # 2. Materialized path: a root uses its bare id, a nested node the parent path + its id.
        node_path = record.node_id if parent_path is None else f"{parent_path}.{record.node_id}"
        out.append(
            FlatNode(
                record=record,
                node_path=node_path,
                depth=depth,
                parent_path=parent_path,
                item_index=item_index,
            )
        )

        # 3. Recurse into the children (group children / per-item body instances).
        for child in record.children:
            cls._walk(child, node_path, depth + 1, item_index, out)


__all__ = ["ExecutionTreeFlattener", "FlatNode"]
