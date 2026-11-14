# ====== Code Summary ======
# Payload capture for execution records at the engine's trace level. One TraceCapture is built per
# FlowEngine and shared by the walker, the action runner and the foreach runner, so every record is
# built with the same ``off`` / ``shape`` / ``full`` rule. It delegates the payload work to
# RecordTrace and holds no run state.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from .trace import RecordTrace, TraceLevel


class TraceCapture:
    """Captures one payload side (input or output) of a record at a fixed trace level."""

    def __init__(self, trace_level: TraceLevel) -> None:
        """
        Args:
            trace_level (TraceLevel): How much of each payload is captured onto its record.
        """
        self._trace_level = trace_level

    def capture(self, payload: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """
        Capture one payload side for a record at the engine's trace level: ``(full_dump, summary)``.

        ``off`` → ``(None, None)``; ``shape`` → only the cheap summary; ``full`` → both the summary
        and the full payload-stripped dump. A None payload (a node that produced nothing) yields
        ``(None, None)`` regardless of level.

        Args:
            payload (Any): The node's resolved input or produced output (a model / list / scalar).

        Returns:
            tuple[dict | None, dict | None]: The full stripped dump (full tier only) and the shape
                summary (shape + full tiers).
        """
        if payload is None:
            return None, None
        summary = RecordTrace.summarize(payload) if self._trace_level.captures_summary else None
        full = RecordTrace.dump(payload) if self._trace_level.captures_full else None
        return full, summary


__all__ = ["TraceCapture"]
