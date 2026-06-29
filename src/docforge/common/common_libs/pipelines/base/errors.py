# ====== Code Summary ======
# The pipeline error hierarchy — the open base every level extends. Each error class carries content
# the backend-driven UI exploits: a stable machine ``code`` AND a human ``description`` of what this
# failure family means. PipelineError is the structured root (failing node identity + code +
# description + context + cause). The engine WRAPS errors recursively up the tree (a child's error
# becomes the ``cause`` of its parent's error), so the cause chain mirrors the node tree.

# ====== Standard Library Imports ======
from typing import Any, ClassVar

# ====== Internal Project Imports ======
from .enums import NodeKind


class PipelineError(Exception):
    """
    Structured root of every pipeline failure.

    Class attributes (exploited by the UI):
        code (str): Stable machine code identifying this failure family.
        description (str): Human-readable description of what this failure means.

    Instance attributes:
        message (str): Human-readable message for this specific occurrence.
        node_key (str | None): Key of the node the failure is attributed to.
        node_kind (NodeKind | None): Level of that node (pipeline/stage/step).
        context (dict[str, Any]): Free-form structured details for observability.
    """

    code: ClassVar[str] = "pipeline_error"
    description: ClassVar[str] = "A failure occurred while running a pipeline."

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
        """Build a structured pipeline error (see the class docstring for the fields)."""
        super().__init__(message)
        self.message = message
        self.node_key = node_key
        self.node_kind = node_kind
        self.code = code or type(self).code
        self.context = context or {}
        if cause is not None:
            self.__cause__ = cause


class ResolutionError(PipelineError):
    """Raised when a declared input binding or required service cannot be resolved."""

    code = "resolution_error"
    description = "A node's input binding or required service could not be resolved."


class NodeError(PipelineError):
    """
    Base for a failure raised by a node's own work — the class stages/steps subclass.

    A concrete step declares its own subclass (e.g. ``OcrError``) with a specific ``code`` +
    ``description`` and may set ``retryable``; the engine records it and wraps it up the tree.

    Class attributes:
        retryable (bool): Hint that the failure may succeed on retry. Advisory only.
    """

    code = "node_error"
    description = "A node failed while doing its work."
    retryable: ClassVar[bool] = False


class StageError(NodeError):
    """Base for stage-level failures."""

    code = "stage_error"
    description = "A stage failed."


class StepError(NodeError):
    """Base for step-level failures."""

    code = "step_error"
    description = "A step failed."


__all__ = [
    "PipelineError",
    "ResolutionError",
    "NodeError",
    "StageError",
    "StepError",
]
