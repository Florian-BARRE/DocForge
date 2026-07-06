"""Live smoke coverage against the REAL running API: discovery, design surface, and a
stages view/apply round trip on the stock ingestion blob.

This is intentionally scoped to the read-only pipeline design surface (no store writes) — the
fuller collections/documents/jobs CRUD battery described in the task brief is a follow-up
(tracked in the final report), since it requires modelling the collections router's request/
response contracts in more depth than the current context budget allows.
"""

import pytest


@pytest.mark.live
def test_discovery_lists_ingest_pipeline(api_client) -> None:
    response = api_client.get("/api/v1/pipelines")
    assert response.status_code == 200, response.text
    index = response.json()["pipelines"]
    assert index[0]["key"] == "ingest"


@pytest.mark.live
def test_design_surface_is_healthy_and_lean_by_default(api_client) -> None:
    response = api_client.get("/api/v1/pipelines/ingest")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["issues"] == []
    assert body["palette"]["run_inputs"] is None


@pytest.mark.live
def test_stages_view_then_apply_round_trip_on_the_real_api(api_client) -> None:
    design = api_client.get("/api/v1/pipelines/ingest").json()
    stock_blob = design["blob"]

    view_response = api_client.post("/api/v1/pipelines/ingest/stages/view", json={"blob": stock_blob})
    assert view_response.status_code == 200, view_response.text
    view_body = view_response.json()
    assert view_body["valid"] is True
    assert view_body["stages"][0]["key"] == "intake"

    apply_response = api_client.post(
        "/api/v1/pipelines/ingest/stages/apply",
        json={"blob": stock_blob, "action": {"action": "disable_stage", "stage": "embed"}},
    )
    assert apply_response.status_code == 200, apply_response.text
    apply_body = apply_response.json()
    assert apply_body["valid"] is True
    assert apply_body["issues"] == []
    assert not any(n["id"] == "embed" for n in apply_body["blob"]["nodes"])


@pytest.mark.live
def test_inspect_a_broken_blob_returns_data_not_an_http_error(api_client) -> None:
    design = api_client.get("/api/v1/pipelines/ingest").json()
    broken = dict(design["blob"])
    broken["nodes"] = [n for n in broken["nodes"] if n["id"] != "parse"]

    response = api_client.post("/api/v1/pipelines/ingest/inspect", json={"blob": broken})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is False
    assert any(issue["code"] == "unknown_node" for issue in body["issues"])
