# ====== Code Summary ======
# Structured progress events emitted by the engine as it runs a graph. The engine calls a
# RunContext.progress_callback at the START and END of every node, so a consumer (e.g. the worker
# pushing SSE for the UI live-status) gets real-time updates without the engine knowing anything
# about the UI. On END the full NodeExecutionRecord is attached.

# ====== Standard Library Imports ======
from collections.abc import Awaitable, Callable
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord


class ProgressPhase(StrEnum):
    """When, relative to a node's execution, a progress event is emitted."""

    START = "start"
    END = "end"


class ProgressEvent(BaseModel):
    """
    A single progress update about one node.

    Attributes:
        phase (ProgressPhase): START (before the node runs) or END (after it finished).
        node_id (str): Identifier of the node.
        kind (str): The node's KIND.
        record (NodeExecutionRecord | None): The execution record — None at START, set at END.
        total_items (int | None): The fan-out width — only set on a ForEach's START event (the
            resolved ``over`` length), so a consumer can render a live "done / total" counter for a
            fan-out stage. None for every other event.
    """

    phase: ProgressPhase
    node_id: str
    kind: str
    record: NodeExecutionRecord | None = None
    total_items: int | None = None


# Async callback the engine invokes for every progress event.
type ProgressCallback = Callable[[ProgressEvent], Awaitable[None]]


__all__ = ["ProgressPhase", "ProgressEvent", "ProgressCallback"]
