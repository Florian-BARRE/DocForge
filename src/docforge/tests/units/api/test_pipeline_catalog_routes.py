"""The parameterized pipeline design surface (Wave 2 seam): the PipelineRegistry now backs the
router, so `GET /pipelines` discovers BOTH ingest and search, `/pipelines/{key}` serves each
pipeline's palette + default blob, and the ingest surface stays byte-identical (non-regression).
The stage rail is ingest-only today: `/pipelines/search/stages/view` 404s and the search index entry
carries no stage URLs.

Uses the real FastAPI app via the `client` fixture (see conftest.py) — the deferred-import rule does
not apply to HTTP calls, only to `from backend...` imports.
"""


def test_index_lists_ingest_and_search(client) -> None:
    """The discovery index now carries both pipeline kinds, ingest first."""
    response = client.get("/api/v1/pipelines")
    assert response.status_code == 200, response.text
    surfaces = {entry["key"]: entry for entry in response.json()["pipelines"]}
    assert set(surfaces) == {"ingest", "search"}

    # 1. Ingest keeps its exact discovery URLs (byte-identical to the hardcoded surface).
    ingest = surfaces["ingest"]
    assert ingest["title"] == "Ingestion pipeline"
    assert ingest["design_url"] == "/api/v1/pipelines/ingest"
    assert ingest["inspect_url"] == "/api/v1/pipelines/ingest/inspect"
    assert ingest["edit_url"] == "/api/v1/pipelines/ingest/edit"
    assert ingest["stages_view_url"] == "/api/v1/pipelines/ingest/stages/view"
    assert ingest["stages_apply_url"] == "/api/v1/pipelines/ingest/stages/apply"

    # 2. Search joins with its own design/inspect URLs but NO stage rail (ingest-coupled today).
    search = surfaces["search"]
    assert search["design_url"] == "/api/v1/pipelines/search"
    assert search["inspect_url"] == "/api/v1/pipelines/search/inspect"
    assert search["stages_view_url"] is None
    assert search["stages_apply_url"] is None


def test_ingest_design_surface_unchanged(client) -> None:
    """The ingest design GET is unchanged: lean palette by default, advanced blocks under ?full."""
    lean = client.get("/api/v1/pipelines/ingest")
    assert lean.status_code == 200, lean.text
    body = lean.json()
    assert body["palette"]["run_inputs"] is None  # lean payload
    assert body["blob"]["id"] == "ingest_pipeline" or body["blob"]["nodes"]  # a real topology
    families = {family["family"] for family in body["palette"]["families"]}
    assert {"intake", "parser", "chunker", "embed"} <= families

    full = client.get("/api/v1/pipelines/ingest", params={"full": "true"})
    assert full.status_code == 200, full.text
    assert full.json()["palette"]["run_inputs"] is not None


def test_search_design_surface(client) -> None:
    """`/pipelines/search` now works: the search palette + the P1 default blob."""
    response = client.get("/api/v1/pipelines/search")
    assert response.status_code == 200, response.text
    body = response.json()

    # 1. The default search topology is the P1 linear graph.
    node_ids = [node["id"] for node in body["blob"]["nodes"]]
    assert node_ids == ["normalize", "encode", "retrieve", "hydrate", "deliver"]
    assert body["issues"] == []  # builds + validates clean

    # 2. Every must-have search family is offered in the palette.
    by_family = {
        family["family"]: {node["kind"] for node in family["nodes"]}
        for family in body["palette"]["families"]
    }
    assert "normalize" in by_family["query"]
    assert "collection" in by_family["encode"]
    assert "hybrid" in by_family["retrieve"]
    assert "hydrate" in by_family["postprocess"]
    assert "hits" in by_family["deliver"]


def test_search_full_palette_carries_advanced_blocks(client) -> None:
    """?full=true flows through the parameterized route for search too."""
    full = client.get("/api/v1/pipelines/search", params={"full": "true"})
    assert full.status_code == 200, full.text
    run_inputs = full.json()["palette"]["run_inputs"]
    assert [slot["name"] for slot in run_inputs] == ["query", "filters", "contract"]


def test_ingest_stage_view_still_responds(client) -> None:
    """The ingest stage view is unchanged — round-trip its own default blob through /stages/view."""
    blob = client.get("/api/v1/pipelines/ingest").json()["blob"]
    response = client.post("/api/v1/pipelines/ingest/stages/view", json={"blob": blob})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["stages"]  # the ordered stage skeleton


def test_search_stage_view_is_404(client) -> None:
    """Search has no stage rail yet — its stage endpoints are an honest 404, not a broken view."""
    blob = client.get("/api/v1/pipelines/search").json()["blob"]
    response = client.post("/api/v1/pipelines/search/stages/view", json={"blob": blob})
    assert response.status_code == 404, response.text


def test_search_inspect_is_generic(client) -> None:
    """Inspect is pipeline-agnostic: it validates the posted search blob under the search key."""
    blob = client.get("/api/v1/pipelines/search").json()["blob"]
    response = client.post("/api/v1/pipelines/search/inspect", json={"blob": blob})
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True


def test_unknown_pipeline_key_is_404(client) -> None:
    """An unknown pipeline kind is a 404 (unlike a broken blob, which is data)."""
    assert client.get("/api/v1/pipelines/nope").status_code == 404
