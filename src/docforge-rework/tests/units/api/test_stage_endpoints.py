"""POST /api/v1/pipelines/ingest/stages/{view,apply} — the product UI's stage rail.

Ported from section 9 of the scratchpad's test_stage_layer.py, plus an API-level equivalent of
test_chains.py::test_chain_step_config_is_completed_build_safe (a SetChain step missing a
required config field is auto-filled '' by the compiler, so /stages/apply always builds even
before the user fills secrets) — see [[port-scratchpad-gap-plan]].
"""


def test_discovery_exposes_the_stage_urls(client) -> None:
    surface = client.get("/api/v1/pipelines").json()["pipelines"][0]
    assert surface["stages_view_url"] == "/api/v1/pipelines/ingest/stages/view"
    assert surface["stages_apply_url"] == "/api/v1/pipelines/ingest/stages/apply"


def test_stages_view_folds_validity_into_one_call(client) -> None:
    stock_blob = client.get("/api/v1/pipelines/ingest").json()["blob"]
    response = client.post("/api/v1/pipelines/ingest/stages/view", json={"blob": stock_blob})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [s["key"] for s in body["stages"]][0] == "intake"  # flattened: stages is the list
    assert body["valid"] is True
    assert body["issues"] == []
    assert body["build_error"] is None


def test_stages_apply_disables_embed_and_unbinds_the_bundle_slot(client) -> None:
    stock_blob = client.get("/api/v1/pipelines/ingest").json()["blob"]
    response = client.post(
        "/api/v1/pipelines/ingest/stages/apply",
        json={"blob": stock_blob, "action": {"action": "disable_stage", "stage": "embed"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["issues"] == []
    assert not any(n["id"] == "embed" for n in body["blob"]["nodes"])
    assert "embeddings" not in body["blob"]["bindings"]["bundle"]
    embed_stage = next(s for s in body["stages"] if s["key"] == "embed")
    assert embed_stage["enabled"] is False
    assert embed_stage["notes"]


def test_stages_apply_set_chain_auto_fills_missing_required_config(client) -> None:
    """A mistral OCR step with an empty config still builds: the compiler auto-fills the
    missing required ``api_key`` with '' so the recompiled blob is ALWAYS buildable, even
    before the user supplies a secret."""
    stock_blob = client.get("/api/v1/pipelines/ingest").json()["blob"]
    response = client.post(
        "/api/v1/pipelines/ingest/stages/apply",
        json={
            "blob": stock_blob,
            "action": {
                "action": "set_chain",
                "stage": "enrich",
                "slot": "scanned_text_ocr",
                "steps": [{"kind": "mistral", "config": {}}],
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["build_error"] is None
    assert body["valid"] is True
    body_of_per_figure = next(n for n in body["blob"]["nodes"] if n["id"] == "per_figure")
    mistral_step = next(n for n in body_of_per_figure["body"]["nodes"] if n["kind"] == "mistral")
    assert mistral_step["config"]["api_key"] == ""
