# ====== Code Summary ======
# Live schema-parity tripwire: fetch a RUNNING DocForge API's /openapi.json and diff every mirrored
# SDK model against it (property names + required fields), reusing the same mapping as the offline
# snapshot test. Unlike the offline guard, this catches a backend model drift the moment it ships —
# no snapshot regeneration required. Opt-in (`-m live`); auto-skips when no API is reachable. Point it
# at a stack with DOCFORGE_E2E_URL (default http://localhost:10040).

# ====== Standard Library Imports ======
import os
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Local Project Imports ======
from tests.parity_map import MODELS

_BASE_URL = os.environ.get("DOCFORGE_E2E_URL", "http://localhost:10040")


def _live_schemas() -> dict[str, Any]:
    """
    Fetch the running API's OpenAPI component schemas, skipping when unreachable.

    Returns:
        dict[str, Any]: The ``components.schemas`` mapping from the live ``/openapi.json``.
    """
    # 1. A missing stack is a skip, not a failure — this suite is opt-in and environment-dependent.
    try:
        response = httpx.get(f"{_BASE_URL}/openapi.json", timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as error:
        pytest.skip(f"live API unreachable at {_BASE_URL}: {error}")
    return response.json()["components"]["schemas"]


@pytest.mark.live
@pytest.mark.parametrize("name", list(MODELS))
def test_property_names_match_live_api(name: str) -> None:
    """Each SDK model's property set must equal the live API schema's property set."""
    api = _live_schemas()[name]
    sdk = MODELS[name].model_json_schema()
    assert set(sdk["properties"]) == set(api["properties"]), name


@pytest.mark.live
@pytest.mark.parametrize("name", list(MODELS))
def test_required_fields_match_live_api(name: str) -> None:
    """Each SDK model's required-field set must equal the live API schema's required set."""
    api = _live_schemas()[name]
    sdk = MODELS[name].model_json_schema()
    assert set(sdk.get("required", [])) == set(api.get("required", [])), name
