# ====== Code Summary ======
# Characterization (safety net) of the dots_ocr_server HTTP surface: the OpenAPI document of create_app()
# is pinned to a committed golden (goldens/openapi.json), so the route set, the request and response
# schemas and the declared status codes cannot change unnoticed. It records TODAY's behaviour on main:
# a diff is a refactor decision to review (shared-core extraction, router moves), never a test to
# fix by regenerating blindly. The app is built without running its lifespan, so no model loads.
#
# To regenerate after a REVIEWED, intended contract change (from src/dots_ocr_server):
#   uv run --frozen python -c "import json; from backend.app import create_app; \
#     print(json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False))" \
#     > tests/characterization/goldens/openapi.json

# ====== Standard Library Imports ======
import json
from pathlib import Path

# ====== Internal Project Imports ======
from backend.app import create_app

GOLDEN_PATH = Path(__file__).parent / "goldens" / "openapi.json"

# (method, path) -> sorted declared response status codes: a readable view of the route set that
# fails with a clear message before the full-document diff does.
EXPECTED_ROUTES = {
    ("GET", "/health"): ["200"],
    ("POST", "/parse"): ["200"],
}


def _routes(schema: dict) -> dict[tuple[str, str], list[str]]:
    """Flatten an OpenAPI document into {(METHOD, path): sorted status codes}."""
    return {
        (method.upper(), path): sorted(operation["responses"])
        for path, item in schema["paths"].items()
        for method, operation in item.items()
    }


def test_route_set_and_declared_status_codes_match_the_recorded_surface() -> None:
    assert _routes(create_app().openapi()) == EXPECTED_ROUTES


def test_openapi_document_matches_the_committed_golden() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert create_app().openapi() == golden


def test_openapi_golden_file_is_the_canonical_serialization() -> None:
    """The golden is stored sorted and indented, so a regeneration produces a minimal diff."""
    raw = GOLDEN_PATH.read_text(encoding="utf-8")
    canonical = json.dumps(json.loads(raw), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert raw == canonical
