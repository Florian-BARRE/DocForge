# ====== Code Summary ======
# Behaviour of GET /health through a TrivialModelServer: 503 "loading" until the service is built, 200
# "ok" once ready, 503 "unhealthy" when a server-specific blocker applies (checked first), the probed
# device in every body, and a richer body model when the server declares one.

# ====== Third-Party Library Imports ======
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from model_server_core import DeviceProbe
from support.fakes.fake_cuda_detector import FakeCudaDetector
from support.fakes.fake_model_service import FakeModelService
from support.fakes.trivial_model_server import TrivialModelServer


def test_loading_until_the_service_is_ready() -> None:
    server = TrivialModelServer(FakeModelService(ready_after_load=False))

    with TestClient(server.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert (body["status"], body["ready"]) == ("loading", False)
    assert body["detail"]


def test_ok_once_the_service_is_ready() -> None:
    server = TrivialModelServer()

    with TestClient(server.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ready": True,
        "detail": None,
        "device": "cpu",
        "model_name": "trivial",
    }


def test_a_blocker_wins_over_readiness_and_is_the_detail() -> None:
    server = TrivialModelServer(blocker="CPU lacks AVX support")

    with TestClient(server.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert response.json()["detail"] == "CPU lacks AVX support"
    assert response.json()["ready"] is False


def test_the_device_comes_from_the_injected_probe() -> None:
    server = TrivialModelServer(device_probe=DeviceProbe([FakeCudaDetector(True)]))

    with TestClient(server.create_app()) as client:
        assert client.get("/health").json()["device"] == "cuda"


def test_health_is_documented_with_the_servers_richer_model() -> None:
    schema = TestClient(TrivialModelServer().create_app()).get("/openapi.json").json()

    health = schema["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]
    assert health["schema"]["$ref"].endswith("TrivialHealthResponse")
