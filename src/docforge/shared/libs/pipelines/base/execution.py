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


class NodeUsage(BaseModel):
    """
    Token accounting for a single PAID text-generation call (LLM / VLM / structgen).

    A non-LLM node leaves this ``None`` on its record. Attached per-leaf so a stage that fans out
    (a VLM foreach over figures) can be totalled — and priced per model — from the execution tree.

    Attributes:
        model (str): The model id the call requested — the key into the pricing table.
        prompt_tokens (int): Input tokens billed for the call.
        completion_tokens (int): Output tokens billed for the call.
    """

    model: str
    prompt_tokens: int
    completion_tokens: int

    @classmethod
    def from_usage_metadata(cls, usage_metadata: object, model: str) -> "NodeUsage | None":
        """
        Build usage from a LangChain ``AIMessage.usage_metadata`` mapping, defensively.

        The capture runs on the hot ingestion loop, so a missing/odd payload (a provider that omits
        usage, a non-int value) MUST yield ``None`` rather than raise — a usage-capture miss can
        never fail a node.

        Args:
            usage_metadata (object): ``AIMessage.usage_metadata`` — a dict with ``input_tokens`` /
                ``output_tokens``, or ``None`` for providers that omit it.
            model (str): The model id the call requested.

        Returns:
            NodeUsage | None: The parsed usage, or None when it cannot be read.
        """
        if not isinstance(usage_metadata, dict):
            return None
        try:
            return cls(
                model=model,
                prompt_tokens=int(usage_metadata["input_tokens"]),
                completion_tokens=int(usage_metadata["output_tokens"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


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
        usage (NodeUsage | None): Token accounting for a paid text-gen leaf; None for every other
            node (groups, foreach wrappers, and non-LLM leaves).
        children (list[NodeExecutionRecord]): Child records when the node is a group.
    """

    node_id: str
    kind: str
    status: NodeStatus
    duration_ms: float
    resolved_input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    usage: NodeUsage | None = None
    children: list["NodeExecutionRecord"] = Field(default_factory=list)


__all__ = ["NodeStatus", "ErrorInfo", "NodeUsage", "NodeExecutionRecord"]
