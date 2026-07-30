"""POST /api/v1/pipelines/ingest/edit — the HTTP round trip for graph editing.

GraphEditor semantics themselves (add/remove/insert/set_binding, EditError messages) are already
covered directly in tests/units/edit/*.py — this file ports ONLY section 6 of the scratchpad's
test_edit_api.py, the real gap per [[port-scratchpad-gap-plan]]: the endpoint contract (happy
path bridges the graph; an impossible op is DATA — 200 + edit_error + the ORIGINAL blob echoed,
never a 500).
"""


def test_edit_endpoint_removes_a_node_and_bridges_the_gap(client) -> None:
    surface = client.get("/api/v1/pipelines").json()["pipelines"][0]
    assert surface["edit_url"] == "/api/v1/pipelines/ingest/edit"
    stock_blob = client.get("/api/v1/pipelines/ingest").json()["blob"]

    response = client.post(
        surface["edit_url"],
        json={
            "blob": stock_blob,
            "operations": [{"op": "remove_node", "node_id": "meta_doc_apply"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["issues"] == []
    assert body["edit_error"] is None
    assert not any(node["id"] == "meta_doc_apply" for node in body["blob"]["nodes"])
    assert any(
        t["from_node_id"] == "meta_doc_loop" and t["to_node_id"] == "embed"
        for t in body["blob"]["transitions"]
    ), "bridged transition must be present in the response blob"


def test_edit_endpoint_returns_data_not_a_500_for_an_impossible_op(client) -> None:
    stock_blob = client.get("/api/v1/pipelines/ingest").json()["blob"]

    response = client.post(
        "/api/v1/pipelines/ingest/edit",
        json={"blob": stock_blob, "operations": [{"op": "remove_node", "node_id": "ghost"}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is False
    assert body["edit_error"]
    assert any(node["id"] == "meta_doc_apply" for node in body["blob"]["nodes"]), (
        "original blob echoed on edit_error"
    )
