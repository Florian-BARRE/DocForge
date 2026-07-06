# ====== Code Summary ======
# The per-node execution record — what happened when a node ran: its status, how long it took,
# the input it resolved, the output it produced, and any error. The engine emits one for EVERY
# node (even on success), and a group's record nests its children's records, so a whole run yields
# a complete execution tree for ultra-fine tracking and UI display.

# ====== Standard Library Imports ======
from enum import StrEnum
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class NodeStatus(StrEnum):
    """
    Outcome of a single node execution.

    Attributes:
        SUCCESS: The node ran and produced its output.
        FAILED: The node raised and the failure propagated (FAIL policy, no recovery edge).
        SKIPPED: The node failed but its SKIP policy let the pipeline continue (its ``error`` is
            still attached, so the trace shows why it was skipped).
    """

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorInfo(BaseModel):
    """
    Captured details of an error raised during a node's execution.

    Attributes:
        error_type (str): The exception class name (e.g. "TimeoutError").
        message (str): The exception message.
        traceback (str | None): The formatted traceback, when captured.
    """

    error_type: str
    message: str
    traceback: str | None = None


class NodeExecutionRecord(BaseModel):
    """
    What happened when one node ran (recursive: a group nests its children's records).

    Attributes:
        node_id (str): Identifier of the executed node.
        kind (str): The node's KIND, to resolve its labels/schema from the registry.
        status (NodeStatus): Outcome of the execution.
        duration_ms (float): Wall-clock execution time in milliseconds.
        resolved_input (dict | None): The input the node consumed, serialised.
        output (dict | None): The output the node produced, serialised.
        error (ErrorInfo | None): Error details when the node failed.
        children (list[NodeExecutionRecord]): Child records when the node is a group.
    """

    node_id: str
    kind: str
    status: NodeStatus
    duration_ms: float
    resolved_input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    children: list["NodeExecutionRecord"] = Field(default_factory=list)


__all__ = ["NodeStatus", "ErrorInfo", "NodeExecutionRecord"]
