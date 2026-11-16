# ====== Code Summary ======
# Reads, writes and compares the conversion corpus snapshot: one JSON file holding, per document
# key, the stable fingerprint of what the pipeline produced. The comparison names every changed
# leaf (path, recorded value, current value) so a drift is readable in a test failure.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "snapshots" / "conversion_corpus.json"
SNAPSHOT_FORMAT_VERSION = 1


class SnapshotMissingError(RuntimeError):
    """No recorded snapshot exists at the expected path (record one first)."""


class SnapshotStore:
    """Persists the recorded fingerprints and diffs a fresh capture against them."""

    def __init__(self, path: Path = SNAPSHOT_PATH) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def save(self, fingerprints: dict[str, Any]) -> None:
        """Writes the fingerprints, sorted and indented so a git diff of the file is meaningful."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format_version": SNAPSHOT_FORMAT_VERSION, "documents": fingerprints}
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load(self) -> dict[str, Any]:
        """Returns the recorded ``documents`` mapping; raises when nothing was recorded."""
        if not self._path.is_file():
            raise SnapshotMissingError(
                f"no conversion snapshot at {self._path} — record one with "
                "DOCFORGE_SMOKE_RECORD=1 (see tests/live/conversion_corpus/README.md)"
            )
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if payload.get("format_version") != SNAPSHOT_FORMAT_VERSION:
            raise SnapshotMissingError(
                f"snapshot format {payload.get('format_version')} != {SNAPSHOT_FORMAT_VERSION}: re-record it"
            )
        return payload["documents"]

    @staticmethod
    def diff(recorded: Any, current: Any, path: str = "") -> list[str]:
        """Lists every leaf that differs between two JSON values, one readable line each."""
        if isinstance(recorded, dict) and isinstance(current, dict):
            lines: list[str] = []
            for key in sorted(set(recorded) | set(current)):
                child = f"{path}.{key}" if path else str(key)
                if key not in recorded:
                    lines.append(f"{child}: added -> {_short(current[key])}")
                elif key not in current:
                    lines.append(f"{child}: removed (was {_short(recorded[key])})")
                else:
                    lines.extend(SnapshotStore.diff(recorded[key], current[key], child))
            return lines
        if (
            isinstance(recorded, list)
            and isinstance(current, list)
            and len(recorded) == len(current)
        ):
            lines = []
            for index, (old, new) in enumerate(zip(recorded, current)):
                lines.extend(SnapshotStore.diff(old, new, f"{path}[{index}]"))
            return lines
        if recorded != current:
            return [f"{path}: {_short(recorded)} -> {_short(current)}"]
        return []


def _short(value: Any, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[: limit - 1] + "…"
