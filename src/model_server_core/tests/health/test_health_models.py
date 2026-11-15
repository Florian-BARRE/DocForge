# ====== Code Summary ======
# Contract of HealthResponse / HealthStatus: the wire shape every model host already returns.

# ====== Third-Party Library Imports ======
import pytest
from pydantic import ValidationError

# ====== Internal Project Imports ======
from model_server_core import HealthResponse, HealthStatus


def test_status_values_are_the_wire_contract() -> None:
    assert [status.value for status in HealthStatus] == ["ok", "loading", "unhealthy"]


def test_the_body_has_the_four_shared_fields_and_detail_defaults_to_none() -> None:
    body = HealthResponse(status="ok", ready=True, device="cpu")

    assert body.model_dump() == {"status": "ok", "ready": True, "detail": None, "device": "cpu"}


def test_status_and_device_stay_plain_strings_in_the_openapi_schema() -> None:
    properties = HealthResponse.model_json_schema()["properties"]

    assert properties["status"]["type"] == "string"
    assert "enum" not in properties["status"]
    assert properties["device"]["type"] == "string"


def test_status_ready_and_device_are_required() -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({"status": "ok"})
