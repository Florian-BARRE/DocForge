# ====== Code Summary ======
# Payload-stripping for execution records. A NodeExecutionRecord is a trace, not a store: re-serialising
# every image crop or embedding vector at every node hop would multiply a document's memory footprint
# several-fold. This helper dumps a model to a dict with heavy payloads — raw bytes and long numeric
# vectors — replaced by compact size placeholders, recursively.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel


class RecordTrace:
    """Static-only helper that dumps a model for an execution record without its heavy payloads."""

    # A numeric list longer than this (an embedding vector) is compacted in the records.
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


__all__ = ["RecordTrace"]
