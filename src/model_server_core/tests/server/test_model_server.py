# ====== Code Summary ======
# Behaviour of the ModelServer base through a trivial concrete subclass (a "5th server"): the abstract
# contract, the assembled app (title, version, routes, health), the lifespan (validate then startup,
# shutdown always), the guards wired from the config, the typed 500, gzip and the injectable parts.

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loggerplusplus.testing import capture

# ====== Internal Project Imports ======
from model_server_core import (
    DeviceProbe,
    ModelServer,
    ServerErrorHandler,
)
from support.fakes.fake_cuda_detector import FakeCudaDetector
from support.fakes.fake_model_service import FakeModelService
from support.fakes.trivial_model_server import TrivialModelServer, TrivialServerConfig


# ── The abstract contract ──────────────────────────────────────────────────────
def test_the_base_class_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError, match="abstract"):
        ModelServer(TrivialServerConfig)  # type: ignore[abstract]


def test_a_subclass_missing_a_member_stays_abstract() -> None:
    class Incomplete(ModelServer[TrivialServerConfig]):
        @property
        def title(self) -> str:
            return "incomplete"

    with pytest.raises(TypeError, match="abstract"):
        Incomplete(TrivialServerConfig)  # type: ignore[abstract]


# ── The assembled app ──────────────────────────────────────────────────────────
def test_the_app_carries_the_servers_title_version_and_routes() -> None:
    app = TrivialModelServer().create_app()

    schema = TestClient(app).get("/openapi.json").json()

    assert schema["info"]["title"] == "Trivial model server"
    assert schema["info"]["version"] == "9.9.9"
    assert {"/health", "/echo", "/check-pdf", "/boom", "/invalid"} <= set(schema["paths"])


def test_the_default_version_is_one_point_zero() -> None:
    class Minimal(TrivialModelServer):
        version = ModelServer.version

    assert Minimal().create_app().version == "1.0.0"


def test_each_create_app_call_builds_an_independent_app() -> None:
    server = TrivialModelServer()

    assert isinstance(server.create_app(), FastAPI)
    assert server.create_app() is not server.create_app()


# ── The lifespan ───────────────────────────────────────────────────────────────
def test_startup_validates_the_config_then_loads_and_shutdown_unloads() -> None:
    server = TrivialModelServer()

    with TestClient(server.create_app()):
        assert server.events == ["startup"]
        assert server.service.calls == ["load"]
        assert server.service.ready is True

    assert server.events == ["startup", "shutdown"]
    assert server.service.calls == ["load", "unload"]


def test_startup_is_narrated_in_the_logs() -> None:
    with capture(level="INFO") as logs:
        with TestClient(TrivialModelServer().create_app()):
            pass

    assert "START Trivial model server" in logs
    assert "END startup of Trivial model server" in logs
    assert "Shutting down Trivial model server" in logs


def test_an_invalid_config_aborts_startup_before_the_model_is_built() -> None:
    class BadConfig(TrivialServerConfig):
        SERVER_PORT = 0

    server = TrivialModelServer()
    server.config = BadConfig

    with pytest.raises(ValueError, match="SERVER_PORT"):
        with TestClient(server.create_app()):
            pass

    assert "load" not in server.service.calls
    assert server.events == ["shutdown"]  # shutdown still runs, and unload is a safe no-op


def test_a_failing_model_load_still_runs_shutdown() -> None:
    server = TrivialModelServer(FakeModelService(fail_on_load=True))

    with pytest.raises(RuntimeError, match="load failed"):
        with TestClient(server.create_app()):
            pass

    assert server.events == ["startup", "shutdown"]
    assert server.service.calls == ["load", "unload"]


# ── The guards, wired from the config ──────────────────────────────────────────
def test_the_body_guard_takes_its_cap_from_the_config() -> None:
    server = TrivialModelServer()
    assert server.body_guard.max_bytes == TrivialServerConfig.MAX_BODY_BYTES == 16

    with TestClient(server.create_app()) as client:
        assert client.post("/echo", content=b"x" * 16).status_code == 200
        assert client.post("/echo", content=b"x" * 17).status_code == 413
        assert client.post("/echo", content=b"").status_code == 422


def test_the_input_validator_takes_its_cap_from_the_config_and_maps_to_422() -> None:
    server = TrivialModelServer()
    assert server.input_validator.max_bytes == 16

    with TestClient(server.create_app()) as client:
        # Reaches the route's InvalidInputError handler (a route raising it) -> clean 422.
        response = client.get("/invalid")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "request body is not a decodable PDF"}}


# ── The typed 500 ──────────────────────────────────────────────────────────────
def test_an_unexpected_route_error_is_a_typed_500_logged_with_its_correlation_id() -> None:
    server = TrivialModelServer(error_handler=ServerErrorHandler(id_factory=lambda: "cid-42"))

    with capture(level="ERROR") as logs:
        with TestClient(server.create_app(), raise_server_exceptions=False) as client:
            response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"]["correlation_id"] == "cid-42"
    assert "weights.bin" not in response.text
    assert "correlation_id=cid-42" in logs
    assert "weights.bin" in logs


# ── The middlewares ────────────────────────────────────────────────────────────
def test_large_responses_are_gzipped_above_the_configured_minimum() -> None:
    class ChattyConfig(TrivialServerConfig):
        GZIP_MINIMUM_SIZE = 10

    server = TrivialModelServer()
    server.config = ChattyConfig

    with TestClient(server.create_app()) as client:
        response = client.get("/openapi.json", headers={"accept-encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"


def test_small_responses_skip_gzip() -> None:
    server = TrivialModelServer()
    server.config = type("QuietConfig", (TrivialServerConfig,), {"GZIP_MINIMUM_SIZE": 10_000_000})

    with TestClient(server.create_app()) as client:
        response = client.get("/health", headers={"accept-encoding": "gzip"})

    assert "content-encoding" not in response.headers


# ── Injection ──────────────────────────────────────────────────────────────────
def test_the_default_device_probe_is_the_torch_free_driver_probe() -> None:
    assert isinstance(TrivialModelServer().device_probe, DeviceProbe)


def test_an_injected_device_probe_is_used() -> None:
    probe = DeviceProbe([FakeCudaDetector(True)])

    assert TrivialModelServer(device_probe=probe).current_device() == "cuda"
