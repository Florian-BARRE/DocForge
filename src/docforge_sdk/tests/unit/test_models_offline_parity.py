# ====== Code Summary ======
# Offline schema-parity guard: every SDK model that mirrors a backend router model must agree with the
# live API's OpenAPI schema (committed as tests/openapi_snapshot.json) on property names and required
# fields. The mapping is keyed by the OpenAPI schema name (which differs from a few SDK class names,
# e.g. FieldSpec ↔ FieldSpecModel). Models with no 1:1 API schema (list wrappers, opaque-blob
# envelopes rendered as raw bytes, SDK-only wrappers) are skipped with an explicit reason.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from tests.parity_map import MODELS as _MODELS
from tests.parity_map import SKIPPED as _SKIPPED

_SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi_snapshot.json"


def _schemas() -> dict[str, Any]:
    """Load the committed OpenAPI component schemas, or skip when the snapshot is missing."""
    if not _SNAPSHOT.exists():
        pytest.skip("OpenAPI snapshot not available — skipping model/API parity check.")
    spec = json.loads(_SNAPSHOT.read_text())
    return spec["components"]["schemas"]


@pytest.mark.parametrize("name", list(_MODELS))
def test_property_names_match_api(name: str) -> None:
    api = _schemas()[name]
    sdk = _MODELS[name].model_json_schema()
    assert set(sdk["properties"]) == set(api["properties"]), name


@pytest.mark.parametrize("name", list(_MODELS))
def test_required_fields_match_api(name: str) -> None:
    api = _schemas()[name]
    sdk = _MODELS[name].model_json_schema()
    assert set(sdk.get("required", [])) == set(api.get("required", [])), name


@pytest.mark.parametrize("name", list(_SKIPPED))
def test_skipped_models_have_a_reason(name: str) -> None:
    # Documents WHY a model is exempt from the API-parity diff so the exemption is explicit, not silent.
    assert _SKIPPED[name]
