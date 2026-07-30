# ====== Code Summary ======
# Offline schema-parity guard: the SDK's mirrored auth models must agree with the live API's OpenAPI
# schema (committed as tests/openapi_snapshot.json) on property names and required fields. If the
# snapshot is absent the test skips with a clear reason so the suite never hard-depends on it.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from pydantic import BaseModel

# ====== Local Project Imports ======
from docforge_sdk.models.auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest

_SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi_snapshot.json"
_MODELS: dict[str, type[BaseModel]] = {
    "CreateKeyRequest": CreateKeyRequest,
    "RotateKeyRequest": RotateKeyRequest,
    "CreatedKey": CreatedKey,
    "KeyInfo": KeyInfo,
}


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
