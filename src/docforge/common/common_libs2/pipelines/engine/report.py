# ====== Code Summary ======
# The feedback tree — a NodeReport is emitted for EVERY node (success or failure), forming a tree
# that mirrors the pipeline -> stage -> step structure. It carries the node status, timing, the keys
# of the inputs that were resolved, and (on failure) a structured ErrorInfo (type/code/where/message)
# extracted from the raised PipelineError. Serialisable Pydantic models so the whole tree is the
# payload the observability API exposes verbatim. ErrorInfo is frozen (an immutable snapshot);
# NodeReport is mutable because the engine fills it in as the node runs.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from ..base import NodeError, PipelineError


class ReportStatus(StrEnum):
    """
    Terminal status of a node within a run.

    Members:
        PENDING: Not yet resolved (transient — never emitted).
        OK: Ran (or aggregated) successfully.
        CACHE_HIT: Served from the node cache without running.
        SKIPPED: Skipped by the engine gate or by a SKIP error policy.
        DEGRADED: Failed but continued under a DEGRADE error policy.
        FAILED: Failed (propagated under a FAIL error policy).
    """

    PENDING = "pending"
    OK = "ok"
    CACHE_HIT = "cache_hit"
    SKIPPED = "skipped"
    DEGRADED = "degraded"
    FAILED = "failed"


class ErrorInfo(BaseModel):
    """
    Structured, serialisable snapshot of a failure, extracted from a raised ``PipelineError``.

    Attributes:
        type (str): The exception class name.
        message (str): The human-readable message.
        code (str | None): The stable machine code.
        where (str | None): The node key the failure is attributed to.
        retryable (bool): Advisory hint carried by ``NodeError`` subclasses.
    """

    model_config = ConfigDict(frozen=True)

    type: str
    message: str
    code: str | None = None
    where: str | None = None
    retryable: bool = False

    @classmethod
    def from_exception(cls, exc: BaseException) -> "ErrorInfo":
        """
        Build an ``ErrorInfo`` from any exception, enriching from ``PipelineError`` when present.

        Args:
            exc (BaseException): The raised exception.

        Returns:
            ErrorInfo: The structured snapshot.
        """
        code = exc.code if isinstance(exc, PipelineError) else None
        where = exc.node_key if isinstance(exc, PipelineError) else None
        retryable = exc.retryable if isinstance(exc, NodeError) else False
        return cls(
            type=type(exc).__name__,
            message=str(exc),
            code=code,
            where=where,
            retryable=retryable,
        )


class NodeReport(BaseModel):
    """
    The execution report of one node — a node of the run's serialisable feedback tree.

    Attributes:
        key (str): The node key.
        kind (str): The node level (pipeline/stage/step).
        status (ReportStatus): Terminal status of the node.
        duration_ms (int): Wall-clock duration of the node.
        inputs (list[str]): Names of the input fields that were resolved.
        error (ErrorInfo | None): The structured failure, when the node failed.
        children (list[NodeReport]): Child reports, in execution order.
    """

    key: str
    kind: str
    status: ReportStatus = ReportStatus.PENDING
    duration_ms: int = 0
    inputs: list[str] = Field(default_factory=list)
    error: ErrorInfo | None = None
    children: list["NodeReport"] = Field(default_factory=list)

    def add_child(self, report: "NodeReport") -> None:
        """Append a child report (in execution order)."""
        self.children.append(report)


NodeReport.model_rebuild()


__all__ = ["ReportStatus", "ErrorInfo", "NodeReport"]
