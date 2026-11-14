# ====== Code Summary ======
# A JSON golden file holding several named snapshots (one per scenario). ``check`` compares a snapshot
# to the stored one and fails with a message that says what the golden is for; with the environment
# variable ``CHARACTERIZATION_REGENERATE=1`` it rewrites the entry instead. A golden is regenerated
# ONLY as a deliberate refactoring decision (see the module docstring of each test using it), never to
# make a red test green.

# ====== Standard Library Imports ======
import json
import os
import pathlib
from typing import Any

REGENERATE_ENV = "CHARACTERIZATION_REGENERATE"


class GoldenFile:
    """A named-snapshot JSON file next to the tests (``goldens/<name>.json``)."""

    def __init__(self, name: str) -> None:
        self._path = pathlib.Path(__file__).resolve().parent.parent / "goldens" / name

    @staticmethod
    def normalise(value: Any) -> Any:
        """Round-trip through JSON so tuples/enums compare like what the file stores."""
        return json.loads(json.dumps(value, default=str))

    def check(self, key: str, actual: Any) -> None:
        """Assert ``actual`` equals the snapshot stored under ``key`` (or rewrite it when regenerating)."""
        actual = self.normalise(actual)
        if os.environ.get(REGENERATE_ENV) == "1":
            snapshots = json.loads(self._path.read_text()) if self._path.exists() else {}
            snapshots[key] = actual
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(snapshots, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            )
            return
        snapshots = json.loads(self._path.read_text())
        assert key in snapshots, f"no snapshot '{key}' in {self._path.name}"
        assert actual == snapshots[key], (
            f"'{key}' drifted from its golden ({self._path.name}). This is a characterization "
            "golden of today's behaviour: a change is a refactoring decision to review, not a test "
            f"to fix. Regenerate on purpose with {REGENERATE_ENV}=1."
        )
