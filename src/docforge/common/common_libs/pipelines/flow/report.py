# ====== Code Summary ======
# The feedback tree the engine emits as it runs — one NodeReport per node (status, timing, error),
# nesting a group's child reports, so even a successful run yields a full pipeline -> ... -> node trace
# for ultra-fine observability. ErrorInfo is recursive (a cause chain) so a failure deep in the tree
# surfaces with its whole lineage. FlowFailure is the internal signal a group raises when a child fails
# with no fallback edge — the parent catches it and wraps the child's ErrorInfo as its cause.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .enums import NodeKind


class ReportStatus(StrEnum):
    """Terminal status of a node in the feedback tree."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"  # vetoed by the should_run gate
    CACHE_HIT = "cache_hit"  # served from the node cache (subtree not run)


class ErrorInfo(BaseModel):
    """A node failure, recursively carrying its cause chain (deepest root cause last)."""

    type: str = Field(description="Exception/failure type name.")
    message: str = Field(description="Failure message.")
    cause: "ErrorInfo | None" = Field(default=None, description="The wrapped underlying cause.")

    @classmethod
    def from_exception(cls, exc: BaseException) -> "ErrorInfo":
        """Build an ErrorInfo from an exception, following its ``__cause__`` chain."""
        cause = exc.__cause__
        return cls(
            type=type(exc).__name__,
            message=str(exc),
            cause=cls.from_exception(cause) if isinstance(cause, BaseException) else None,
        )


class NodeReport(BaseModel):
    """
    Self-describing outcome of one node — nests a group's child reports into the feedback tree.

    Attributes:
        id (str): The node id.
        kind (NodeKind): action | group.
        status (ReportStatus): The node's terminal status.
        duration_ms (int): Wall-clock duration.
        error (ErrorInfo | None): The failure (with its cause chain) when status is FAILED.
        children (list[NodeReport]): Child reports, in execution order (a group only).
    """

    id: str
    kind: NodeKind
    status: ReportStatus = ReportStatus.PENDING
    duration_ms: int = 0
    error: ErrorInfo | None = None
    children: list["NodeReport"] = Field(default_factory=list)


ErrorInfo.model_rebuild()
NodeReport.model_rebuild()


class FlowFailure(Exception):
    """Internal signal: a group child failed with no fallback edge — carries the child's ErrorInfo."""

    def __init__(self, error_info: ErrorInfo, message: str) -> None:
        """
        Args:
            error_info (ErrorInfo): The failing child's error (becomes the parent's cause).
            message (str): The group-level failure message.
        """
        self.error_info = error_info
        super().__init__(message)


__all__ = ["ReportStatus", "ErrorInfo", "NodeReport", "FlowFailure"]
