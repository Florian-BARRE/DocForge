# ====== Code Summary ======
# FailureBreadcrumb — the single source of truth for WHERE a run died. It walks a failed execution
# record depth-first to the deepest node that actually raised (a group's own error is None; the fatal
# cause is a FAILED leaf nested in its children) and captures it structurally: the node, its kind, the
# exception type/message, and — when the failure sits inside a fan-out — the item index (the engine
# renames each foreach item's record to ``<body>[<index>]``). Both the job's free-text error string
# and its structured breadcrumb columns are derived from this ONE object.

# ====== Standard Library Imports ======
import re

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus

# A foreach stamps each item's record node_id as ``<body_id>[<index>]`` — the fan-out item marker.
_ITEM_INDEX_RE = re.compile(r"\[(\d+)\]$")


class FailureBreadcrumb(BaseModel):
    """The deepest node that raised in a failed run, located structurally.

    Attributes:
        node_id (str): The failing node's id.
        node_kind (str): The failing node's kind.
        error_type (str): The exception class name (e.g. "TimeoutError").
        message (str): The exception message.
        item_index (int | None): The fan-out item index the failure sits in (None outside a fan-out).
    """

    node_id: str
    node_kind: str
    error_type: str
    message: str
    item_index: int | None = None

    @classmethod
    def from_record(
        cls, record: NodeExecutionRecord, item_index: int | None = None
    ) -> "FailureBreadcrumb | None":
        """
        Find the deepest failed node in an execution record and describe it.

        Args:
            record (NodeExecutionRecord): The record to walk (recursed into its children).
            item_index (int | None): The fan-out item index inherited from an ancestor foreach frame.

        Returns:
            FailureBreadcrumb | None: The breadcrumb for the failing node, or None when no FAILED
            leaf in this subtree carries an error.
        """
        # 1. Adopt this frame's fan-out item index if its node_id encodes one (``<body>[<index>]``).
        match = _ITEM_INDEX_RE.search(record.node_id)
        current_index = int(match.group(1)) if match else item_index

        # 2. Depth-first — a nested failure is more specific than the group above it.
        for child in record.children:
            found = cls.from_record(child, current_index)
            if found is not None:
                return found

        # 3. This node is the culprit only if it FAILED with a captured error.
        if record.status == NodeStatus.FAILED and record.error is not None:
            return cls(
                node_id=record.node_id,
                node_kind=record.kind,
                error_type=record.error.error_type,
                message=record.error.message,
                item_index=current_index,
            )
        return None

    @property
    def reason(self) -> str:
        """Human-readable one-line reason: ``node (kind)[ item N]: ErrorType: message``."""
        location = f" item {self.item_index}" if self.item_index is not None else ""
        return f"{self.node_id} ({self.node_kind}){location}: {self.error_type}: {self.message}"


__all__ = ["FailureBreadcrumb"]
