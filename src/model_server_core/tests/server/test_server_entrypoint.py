# ====== Code Summary ======
# Behaviour of ServerEntrypoint: it applies the logging bootstrap, exposes the assembled app, and runs
# the (injected) ASGI runner with the configured host and port; it adds no logic of its own.

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from model_server_core import ServerEntrypoint
from support.fakes.trivial_model_server import TrivialModelServer, TrivialServerConfig


class _RecordingRunner:
    """Stands in for uvicorn.run and records how it was called."""

    def __init__(self) -> None:
        self.calls: list[tuple[FastAPI, str, int]] = []

    def __call__(self, app: FastAPI, *, host: str, port: int) -> None:
        self.calls.append((app, host, port))


def test_the_entrypoint_exposes_the_assembled_app() -> None:
    entrypoint = ServerEntrypoint(TrivialModelServer(), runner=_RecordingRunner())

    assert isinstance(entrypoint.app, FastAPI)
    with TestClient(entrypoint.app) as client:
        assert client.get("/health").status_code == 200


def test_run_serves_the_app_on_the_configured_host_and_port() -> None:
    runner = _RecordingRunner()
    entrypoint = ServerEntrypoint(TrivialModelServer(), runner=runner)

    entrypoint.run()

    assert runner.calls == [
        (entrypoint.app, TrivialServerConfig.SERVER_HOST, TrivialServerConfig.SERVER_PORT)
    ]


def test_the_logging_bootstrap_is_applied_from_the_server_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ServerEntrypoint(TrivialModelServer(), runner=_RecordingRunner())

    loggerplusplus.bind(identifier="Probe").info("after entrypoint")

    assert "after entrypoint" in capsys.readouterr().out


def test_the_app_is_built_once_at_construction() -> None:
    entrypoint = ServerEntrypoint(TrivialModelServer(), runner=_RecordingRunner())

    assert entrypoint.app is entrypoint.app
