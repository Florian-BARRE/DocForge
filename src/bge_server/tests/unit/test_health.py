# ====== Code Summary ======
# Unit tests for GET /health, served by the core HealthRoute through BgeServer: the `device` field
# the DocForge /capabilities probe reads (exactly "cpu" or "cuda"; on this CPU CI/dev box the torch
# probe resolves to "cpu"), the two model identities, and the readiness rule of BgeModelsService
# (embed loaded, and the reranker too unless BGE_LOAD_RERANKER is off). Torch-free: the models are
# marked loaded through the service's private sentinels, no weights involved.

# ====== Third-Party Library Imports ======
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend import BgeServer
from config_loader import BgeServerConfig
from tests.support.bge_app import build_server


class _NoRerankerConfig(BgeServerConfig):
    """An embed-only deployment (BGE_LOAD_RERANKER=false)."""

    BGE_LOAD_RERANKER = False


def _client(server: BgeServer, embed_loaded: bool, reranker_loaded: bool) -> TestClient:
    """A TestClient over the real app (no lifespan → no real load) with the given model state."""
    server.models._embed_model = object() if embed_loaded else None  # type: ignore[assignment]
    server.models._reranker = object() if reranker_loaded else None  # type: ignore[assignment]
    return TestClient(server.create_app())


def test_health_reports_device_and_model_ids_when_ready() -> None:
    response = _client(build_server(), embed_loaded=True, reranker_loaded=True).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ready"] is True
    assert body["device"] in {"cpu", "cuda"}
    assert body["embed_model"] == BgeServerConfig.BGE_M3_MODEL
    assert body["rerank_model"] == BgeServerConfig.BGE_RERANKER_MODEL


def test_health_reports_device_while_loading() -> None:
    response = _client(build_server(), embed_loaded=False, reranker_loaded=False).get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "loading"
    assert body["ready"] is False
    assert body["device"] in {"cpu", "cuda"}


def test_health_is_loading_while_only_the_embed_model_is_loaded() -> None:
    """With the reranker expected, an embed-only half-load is still not ready."""
    response = _client(build_server(), embed_loaded=True, reranker_loaded=False).get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "loading"


def test_health_is_ready_when_reranker_gated_off() -> None:
    """
    An embed-only deployment (BGE_LOAD_RERANKER=false) never loads the reranker — the health
    probe must still report ready once the embed model alone is loaded, not perpetually "loading".
    """
    server = build_server(config=_NoRerankerConfig)
    response = _client(server, embed_loaded=True, reranker_loaded=False).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
