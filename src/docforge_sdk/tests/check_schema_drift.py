# ====== Code Summary ======
# CI helper (not a pytest module — no test_*/​*_test naming, so pytest never collects it, matching
# parity_map.py's convention) — diffs the CURRENT backend OpenAPI schema (dumped serviceless by
# src/docforge/app/scripts/dump_openapi.py) against the committed tests/openapi_snapshot.json
# on exactly the schemas the SDK mirrors (tests/parity_map.MODELS — the single source of truth also
# used by the offline and live parity tests, so this can never drift from them). A raw full-file diff
# is too brittle (FastAPI may reorder keys across runs); this compares only property names + required
# sets per tracked schema, the same contract test_models_offline_parity.py enforces. On drift, prints
# a fix instruction and exits non-zero — the CI gate that makes SDK/backend drift impossible to merge.
#
# Usage: uv run python tests/check_schema_drift.py <path-to-current-openapi.json>

# ====== Standard Library Imports ======
import json
import sys
from pathlib import Path
from typing import Any

# ====== Local Project Imports ======
from tests.parity_map import MODELS

_SNAPSHOT = Path(__file__).resolve().parent / "openapi_snapshot.json"

_FIX_MESSAGE = (
    "backend API changed — regenerate src/docforge_sdk/tests/openapi_snapshot.json (via "
    "`uv run python app/scripts/dump_openapi.py` from src/docforge/) and reconcile the SDK "
    "models in src/docforge_sdk/docforge_sdk/models/."
)


def _load_schemas(path: Path) -> dict[str, Any]:
    """Load the `components.schemas` mapping from an OpenAPI document on disk."""
    spec = json.loads(path.read_text())
    return spec["components"]["schemas"]


def _diff_schema(name: str, snapshot: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Compare one tracked schema's property names + required set between the two documents.

    Args:
        name (str): The OpenAPI component-schema name being compared.
        snapshot (dict[str, Any]): The committed schema definition.
        current (dict[str, Any]): The freshly-dumped schema definition.

    Returns:
        list[str]: Human-readable mismatch lines; empty when the two agree.
    """
    problems: list[str] = []

    snapshot_props = set(snapshot.get("properties", {}))
    current_props = set(current.get("properties", {}))
    if snapshot_props != current_props:
        added = current_props - snapshot_props
        removed = snapshot_props - current_props
        problems.append(
            f"{name}: properties differ (added={sorted(added)}, removed={sorted(removed)})"
        )

    snapshot_required = set(snapshot.get("required", []))
    current_required = set(current.get("required", []))
    if snapshot_required != current_required:
        added = current_required - snapshot_required
        removed = snapshot_required - current_required
        problems.append(
            f"{name}: required fields differ (added={sorted(added)}, removed={sorted(removed)})"
        )

    return problems


def main() -> int:
    """Compare the tracked schemas between the committed snapshot and a freshly-dumped OpenAPI doc.

    Returns:
        int: Process exit code — 0 when every tracked schema matches, 1 on any drift or missing schema.
    """
    # 1. A current-openapi.json path is mandatory — this script has no live/offline fallback of its own.
    if len(sys.argv) != 2:
        print("usage: check_schema_drift.py <path-to-current-openapi.json>", file=sys.stderr)
        return 2
    current_path = Path(sys.argv[1])

    # 2. Load both documents' component schemas.
    snapshot_schemas = _load_schemas(_SNAPSHOT)
    current_schemas = _load_schemas(current_path)

    # 3. Diff every schema the SDK mirrors (tests/parity_map.MODELS — shared with the pytest guards).
    problems: list[str] = []
    for name in MODELS:
        if name not in snapshot_schemas:
            problems.append(
                f"{name}: missing from the committed snapshot (add it to openapi_snapshot.json)"
            )
            continue
        if name not in current_schemas:
            problems.append(
                f"{name}: missing from the current backend OpenAPI (renamed or removed?)"
            )
            continue
        problems.extend(_diff_schema(name, snapshot_schemas[name], current_schemas[name]))

    # 4. Report.
    if problems:
        print("SDK <-> backend OpenAPI contract drift detected:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(f"\n{_FIX_MESSAGE}", file=sys.stderr)
        return 1

    print(f"OK — {len(MODELS)} tracked schemas match the committed snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
