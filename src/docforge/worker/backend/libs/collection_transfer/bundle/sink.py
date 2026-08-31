# ====== Code Summary ======
# JsonlSink — a streaming, self-hashing writer for one JSONL file of the bundle. Rows are written one
# line at a time (never a whole table buffered in memory), while a running sha256 and a line count
# are maintained so the writer can record the file's integrity entry the moment it closes. The JSON
# encoder tolerates the value types that leak out of the ORM/JSONB layer (uuid, datetime, Decimal).

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _json_default(value: Any) -> Any:
    """Encode the non-native types that surface from the ORM / JSONB layer."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class JsonlSink:
    """A single JSONL file opened for streaming, hashing writes (one row per line)."""

    def __init__(self, path: pathlib.Path) -> None:
        """
        Args:
            path (pathlib.Path): The absolute file path inside the bundle working directory.
        """
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("wb")
        self._hasher = hashlib.sha256()
        self._size = 0
        self.rows = 0

    def write(self, row: dict[str, Any]) -> None:
        """Serialize one row to a single JSONL line, updating the running hash and size."""
        line = json.dumps(row, default=_json_default, ensure_ascii=False).encode("utf-8") + b"\n"
        self._handle.write(line)
        self._hasher.update(line)
        self._size += len(line)
        self.rows += 1

    def close(self) -> tuple[str, int]:
        """Flush and close the file, returning its (sha256_hex, size_bytes)."""
        self._handle.close()
        return self._hasher.hexdigest(), self._size

    def __enter__(self) -> JsonlSink:
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self._handle.closed:
            self._handle.close()


__all__ = ["JsonlSink"]
