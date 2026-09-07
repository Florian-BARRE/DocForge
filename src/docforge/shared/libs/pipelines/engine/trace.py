# ====== Code Summary ======
# Trace capture for execution records. Two concerns live here:
#   - TraceLevel: the three-level capture verbosity an engine runs at (off / shape / full), with the
#     off < shape < full ordering a global ceiling clamps a per-collection request against.
#   - RecordTrace: turns a node payload into what a NodeExecutionRecord carries. ``summarize`` is the
#     always-affordable SHAPE descriptor (a cheap SHALLOW look at the payload — top-level fields, list
#     lengths, byte/char sizes, a stable fingerprint — never a deep model_dump); ``dump`` is the FULL
#     stripped payload (heavy bytes/vectors replaced by size placeholders), used only at the full tier.

# ====== Standard Library Imports ======
import hashlib
import json
from enum import StrEnum
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel


class TraceLevel(StrEnum):
    """
    How much of each node's input/output an execution run captures onto its record.

    Ordered ``off < shape < full``: a per-collection request is clamped by a global operator ceiling
    (``TraceLevel.clamp``), so an operator can forbid ``full`` fleet-wide regardless of a collection's
    own setting.

    Attributes:
        OFF: Capture nothing (the search runner's mode — the record is discarded, so no work is spent).
        SHAPE: Capture only the cheap shallow SHAPE descriptor inline on the row (the ingest default —
            no raw content ever at rest).
        FULL: Capture the SHAPE descriptor AND the full stripped payload (the latter stored in the
            object store by content hash; opt-in per collection, clamped by the ceiling).
    """

    OFF = "off"
    SHAPE = "shape"
    FULL = "full"

    @property
    def _rank(self) -> int:
        """The level's position in the off < shape < full ordering (for clamping/comparison)."""
        return {TraceLevel.OFF: 0, TraceLevel.SHAPE: 1, TraceLevel.FULL: 2}[self]

    @property
    def captures_summary(self) -> bool:
        """True when this level attaches the SHAPE summary (shape and full tiers)."""
        return self is TraceLevel.SHAPE or self is TraceLevel.FULL

    @property
    def captures_full(self) -> bool:
        """True when this level also retains the full stripped payload (full tier only)."""
        return self is TraceLevel.FULL

    def clamp(self, ceiling: "TraceLevel") -> "TraceLevel":
        """Return the LOWER of this level and ``ceiling`` (off < shape < full) — the operator cap."""
        return self if self._rank <= ceiling._rank else ceiling


class RecordTrace:
    """Static-only helper that turns a node payload into its execution-record trace (shape / full)."""

    # A numeric list longer than this (an embedding vector) is compacted in the full-tier dump.
    NUMERIC_LIST_LIMIT = 64

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RecordTrace is a static-only class and cannot be instantiated.")

    @classmethod
    def strip_payloads(cls, value: Any) -> Any:
        """Replace heavy payloads (bytes, long numeric lists) with size placeholders, recursively."""
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        if isinstance(value, dict):
            return {key: cls.strip_payloads(item) for key, item in value.items()}
        if isinstance(value, list):
            # An embedding vector in a trace is dead weight — keep its size, drop its numbers.
            if len(value) > cls.NUMERIC_LIST_LIMIT and all(
                isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
            ):
                return f"<{len(value)} numbers>"
            return [cls.strip_payloads(item) for item in value]
        return value

    @classmethod
    def dump(cls, model: BaseModel) -> dict[str, Any]:
        """Dump a model for an execution record WITHOUT its heavy payloads (crops, vectors…) — a
        record is a trace, not a store; re-serialising every image or embedding at every hop
        multiplies a document's memory footprint several-fold."""
        return cls.strip_payloads(model.model_dump())

    @classmethod
    def summarize(cls, payload: Any) -> dict[str, Any]:
        """
        Build the cheap SHAPE descriptor of a node payload — the always-on trace tier.

        Deliberately SHALLOW: it never calls ``model_dump`` (that full traversal, rebuilding a giant
        nested dict at every IR-carrying hop, is exactly what the full tier pays for and the shape
        tier must not). It looks only at the payload's top-level shape — its type, its field names,
        the length of any list-valued field and the byte/char size of any bytes/str field — plus a
        stable fingerprint of that descriptor.

        Args:
            payload (Any): The node's resolved input or produced output (a pydantic model, a list of
                artefacts, or a scalar).

        Returns:
            dict[str, Any]: The shape descriptor (``{type, fields, sizes, item_count, hash}`` for a
                model; ``{type, item_count, element_type, hash}`` for a list; ``{type, sizes?, hash}``
                for a scalar).
        """
        if isinstance(payload, BaseModel):
            return cls.__summarize_model(payload)
        if isinstance(payload, list):
            return cls.__summarize_list(payload)
        return cls.__summarize_scalar(payload)

    @classmethod
    def __summarize_model(cls, payload: BaseModel) -> dict[str, Any]:
        """Shape descriptor of a pydantic model — field names + cheap per-field sizes/counts."""
        # 1. Top-level field names come straight off the class (no instance traversal).
        fields = list(type(payload).model_fields)

        # 2. Cheap per-field measures: byte/char size of bytes/str fields, length of list fields. A
        #    nested model is NOT descended into — that is the deep traversal the shape tier avoids.
        sizes: dict[str, int] = {}
        item_count: dict[str, int] = {}
        for name in fields:
            value = getattr(payload, name, None)
            if isinstance(value, (bytes, bytearray, str)):
                sizes[name] = len(value)
            elif isinstance(value, list):
                item_count[name] = len(value)

        descriptor: dict[str, Any] = {
            "type": type(payload).__name__,
            "fields": fields,
            "sizes": sizes,
            "item_count": item_count,
        }
        descriptor["hash"] = cls.__fingerprint(descriptor)
        return descriptor

    @classmethod
    def __summarize_list(cls, payload: list[Any]) -> dict[str, Any]:
        """Shape descriptor of a list payload (a ``list[Artifact]`` slot) — length + element type."""
        descriptor: dict[str, Any] = {
            "type": "list",
            "item_count": len(payload),
            "element_type": type(payload[0]).__name__ if payload else None,
        }
        descriptor["hash"] = cls.__fingerprint(descriptor)
        return descriptor

    @classmethod
    def __summarize_scalar(cls, payload: Any) -> dict[str, Any]:
        """Shape descriptor of a scalar payload — its type and (for sized scalars) its length."""
        descriptor: dict[str, Any] = {"type": type(payload).__name__}
        if isinstance(payload, (bytes, bytearray, str)):
            descriptor["sizes"] = {"value": len(payload)}
        descriptor["hash"] = cls.__fingerprint(descriptor)
        return descriptor

    @staticmethod
    def __fingerprint(descriptor: dict[str, Any]) -> str:
        """A stable sha256 over the shape descriptor — a cheap fingerprint (shape + sizes), not a
        deep content hash: two payloads of identical shape and sizes share it, so it flags a
        shape/size change across a hop without ever serialising the payload's content."""
        canonical = json.dumps(descriptor, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


__all__ = ["TraceLevel", "RecordTrace"]
