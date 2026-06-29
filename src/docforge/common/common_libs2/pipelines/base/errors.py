# ====== Code Summary ======
# The pipeline error hierarchy — the open base every level extends for ultra-fine error tracking.
# PipelineError is the structured root (it carries the failing node's identity, a machine code, a
# free-form context dict, and the original cause). ResolutionError is raised by the resolver when a
# declared binding/capability cannot be satisfied. NodeError is the base a STAGE or STEP subclasses
# to declare its own domain failure modes (e.g. a ConversionError, an OcrError) — each with its own
# code and context, so the NodeReport can surface exactly what failed and where.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Local Project Imports ======
from .enums import NodeKind


class PipelineError(Exception):
    """
    Structured root of every pipeline failure.

    Attributes:
        message (str): Human-readable error message.
        node_key (str | None): Key of the node the failure is attributed to.
        node_kind (NodeKind | None): Level of that node (pipeline/stage/step).
        code (str): Stable machine code (defaults to the class-level ``code``).
        context (dict[str, Any]): Free-form structured details for observability.
    """

    code: str = "pipeline_error"

    def __init__(
        self,
        message: str,
        *,
        node_key: str | None = None,
        node_kind: NodeKind | None = None,
        code: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        """Build a structured pipeline error (see class attributes for the fields)."""
        super().__init__(message)
        self.message = message
        self.node_key = node_key
        self.node_kind = node_kind
        self.code = code or type(self).code
        self.context = context or {}
        if cause is not None:
            self.__cause__ = cause


class ResolutionError(PipelineError):
    """Raised when a declared input binding or required capability cannot be resolved."""

    code = "resolution_error"


class NodeError(PipelineError):
    """
    Base for a failure raised by a node's own work — the class stages/steps subclass.

    A concrete step declares its own subclass (e.g. ``OcrError``) with a specific ``code`` and may
    set ``retryable``; the engine records it in the NodeReport and then applies the node's
    declarative error policy (which stays authoritative).

    Attributes:
        retryable (bool): Hint that the failure may succeed on retry. Advisory only.
    """

    code = "node_error"
    retryable: bool = False


class StageError(NodeError):
    """Base for stage-specific failures."""

    code = "stage_error"


class StepError(NodeError):
    """Base for step-specific failures."""

    code = "step_error"


__all__ = [
    "PipelineError",
    "ResolutionError",
    "NodeError",
    "StageError",
    "StepError",
]
