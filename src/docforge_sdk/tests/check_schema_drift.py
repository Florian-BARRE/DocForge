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
# ALSO checks completeness against the CURRENT (freshly-dumped) document — not just the committed
# snapshot — for both schemas (every components.schemas name must be in MODELS or SKIPPED) and routes
# (every path+method must be in ROUTES or EXEMPT_ROUTES). This is what actually catches a brand-new
# backend endpoint the moment it ships: the snapshot-only pytest guards would stay green until someone
# remembers to regenerate openapi_snapshot.json, but this script runs against the CURRENT API on every
# PR (see .github/workflows/gate.yml, job `sdk-parity`).
#
# Usage: uv run python tests/check_schema_drift.py <path-to-current-openapi.json>

# ====== Standard Library Imports ======
import json
import sys
from pathlib import Path
from typing import Any

# ====== Local Project Imports ======
from tests.parity_map import MODELS, SKIPPED
from tests.route_map import EXEMPT_ROUTES, ROUTES

_SNAPSHOT = Path(__file__).resolve().parent / "openapi_snapshot.json"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

_FIX_MESSAGE = (
    "backend API changed — regenerate src/docforge_sdk/tests/openapi_snapshot.json (via "
    "`uv run python app/scripts/dump_openapi.py` from src/docforge/) and reconcile the SDK "
    "models in src/docforge_sdk/docforge_sdk/models/."
)

_COMPLETENESS_FIX_MESSAGE = (
    "a NEW backend schema/route was found with no SDK coverage and no reasoned exemption — mirror it "
    "into src/docforge_sdk/docforge_sdk/models/ (+ tests/parity_map.MODELS) or resources/ (+ "
    "tests/route_map.ROUTES), or explicitly exempt it (tests/parity_map.SKIPPED / "
    "tests/route_map.EXEMPT_ROUTES) with a reason."
)


def _load_spec(path: Path) -> dict[str, Any]:
    """Load a full OpenAPI document from disk."""
    spec: dict[str, Any] = json.loads(path.read_text())
    return spec


def _load_schemas(path: Path) -> dict[str, Any]:
    """Load the `components.schemas` mapping from an OpenAPI document on disk."""
    return _load_spec(path)["components"]["schemas"]


def _current_routes(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """
    Extract every (METHOD, path) operation from an OpenAPI document.

    Args:
        spec (dict[str, Any]): A full, parsed OpenAPI document.

    Returns:
        set[tuple[str, str]]: One ``(HTTP method, path)`` pair per operation in ``paths``.
    """
    return {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
        if method in _HTTP_METHODS
    }


def _completeness_problems(current_spec: dict[str, Any]) -> list[str]:
    """
    Check the CURRENT OpenAPI document for schemas/routes with neither SDK coverage nor an exemption.

    Args:
        current_spec (dict[str, Any]): The freshly-dumped, full OpenAPI document.

    Returns:
        list[str]: One line per untracked schema or route; empty when everything is accounted for.
    """
    problems: list[str] = []

    # 1. Every current component schema must be mirrored (MODELS) or exempted (SKIPPED).
    tracked_schemas = set(MODELS) | set(SKIPPED)
    untracked_schemas = set(current_spec["components"]["schemas"]) - tracked_schemas
    problems.extend(f"untracked schema: {name}" for name in sorted(untracked_schemas))

    # 2. Every current route must be wired (ROUTES) or exempted (EXEMPT_ROUTES).
    tracked_routes = ROUTES | set(EXEMPT_ROUTES)
    untracked_routes = _current_routes(current_spec) - tracked_routes
    problems.extend(
        f"untracked route: {method} {path}" for method, path in sorted(untracked_routes)
    )

    return problems


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

    # 2. Load both documents (full spec for the current one — completeness needs `paths` too).
    snapshot_schemas = _load_schemas(_SNAPSHOT)
    current_spec = _load_spec(current_path)
    current_schemas = current_spec["components"]["schemas"]

    # 3. Diff every schema the SDK mirrors (tests/parity_map.MODELS — shared with the pytest guards).
    drift_problems: list[str] = []
    for name in MODELS:
        if name not in snapshot_schemas:
            drift_problems.append(
                f"{name}: missing from the committed snapshot (add it to openapi_snapshot.json)"
            )
            continue
        if name not in current_schemas:
            drift_problems.append(
                f"{name}: missing from the current backend OpenAPI (renamed or removed?)"
            )
            continue
        drift_problems.extend(_diff_schema(name, snapshot_schemas[name], current_schemas[name]))

    # 4. Additive-drift guard: every CURRENT schema/route must be tracked or explicitly exempted —
    #    catches a brand-new endpoint the moment it ships, before anyone regenerates the snapshot.
    completeness_problems = _completeness_problems(current_spec)

    # 5. Report both kinds of problem, each with its own fix instruction.
    if drift_problems or completeness_problems:
        print("SDK <-> backend OpenAPI contract drift detected:", file=sys.stderr)
        for problem in drift_problems:
            print(f"  - {problem}", file=sys.stderr)
        for problem in completeness_problems:
            print(f"  - {problem}", file=sys.stderr)
        if drift_problems:
            print(f"\n{_FIX_MESSAGE}", file=sys.stderr)
        if completeness_problems:
            print(f"\n{_COMPLETENESS_FIX_MESSAGE}", file=sys.stderr)
        return 1

    print(
        f"OK — {len(MODELS)} tracked schemas match the committed snapshot; "
        f"{len(current_schemas)} current schemas and {len(_current_routes(current_spec))} current "
        "routes are fully accounted for (MODELS/SKIPPED, ROUTES/EXEMPT_ROUTES)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
