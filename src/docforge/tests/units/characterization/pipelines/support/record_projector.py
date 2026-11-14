# ====== Code Summary ======
# Projects the engine's observable output onto plain, deterministic data a golden can compare: a
# NodeExecutionRecord tree without its wall-clock durations and tracebacks, and a progress-event log
# without its record payloads. Everything that varies between two runs (durations, traceback text,
# pydantic's documentation URLs) is dropped; everything a refactor must keep (ids, kinds, statuses,
# error types and messages, scores, nesting, summary shapes) is kept.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.pipelines.engine import ProgressEvent


class RecordProjector:
    """Static-only helper: record trees and progress events → comparable plain data."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RecordProjector is a static-only class and cannot be instantiated.")

    @classmethod
    def record(cls, record: NodeExecutionRecord, with_summaries: bool = False) -> dict[str, Any]:
        """
        Project a record tree: id, kind, status, error, score, output shape, children.

        Args:
            record (NodeExecutionRecord): The record to project (recursively).
            with_summaries (bool): Also keep the ``input_summary`` / ``output_summary`` shape
                descriptors (the engine's output summary shapes), and the ``output`` dump of a
                ForEach wrapper.

        Returns:
            dict[str, Any]: The projection; ``error`` is ``None`` or ``{type, message}``.
        """
        projected: dict[str, Any] = {
            "node_id": record.node_id,
            "kind": record.kind,
            "status": record.status.value,
            "error": cls.error(record),
            "score": record.score,
        }
        if with_summaries:
            projected["input_summary"] = cls.summary(record.input_summary)
            projected["output_summary"] = cls.summary(record.output_summary)
            projected["output"] = record.output
        projected["children"] = [cls.record(child, with_summaries) for child in record.children]
        return projected

    @staticmethod
    def summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
        """A shape summary with its fingerprint cut to 8 hex characters: still a drift detector, but
        short enough not to read as a secret to the repository's secret scanner."""
        if summary is None:
            return None
        return {**summary, "hash": str(summary["hash"])[:8]}

    @staticmethod
    def error(record: NodeExecutionRecord) -> dict[str, str] | None:
        """The record's error as ``{type, message}`` — the first message line only, so a pydantic
        validation message (whose later lines embed a version-specific documentation URL) stays stable."""
        if record.error is None:
            return None
        return {
            "type": record.error.error_type,
            "message": record.error.message.splitlines()[0] if record.error.message else "",
        }

    @staticmethod
    def event(event: ProgressEvent) -> tuple[str, str, str, int | None, str | None]:
        """A progress event as ``(phase, node_id, kind, total_items, record status or None)``."""
        status = event.record.status.value if event.record is not None else None
        return (event.phase.value, event.node_id, event.kind, event.total_items, status)

    @staticmethod
    def flat(record: NodeExecutionRecord) -> list[tuple[str, str, str]]:
        """The record tree flattened depth-first, parent before children: ``(node_id, kind, status)``."""
        rows = [(record.node_id, record.kind, record.status.value)]
        for child in record.children:
            rows.extend(RecordProjector.flat(child))
        return rows
