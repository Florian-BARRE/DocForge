# ====== Code Summary ======
# API tests for GET /api/v1/discovery — per-endpoint contracts (from the app's OpenAPI) + dynamic
# overlays (pipeline choices; collection-scoped search filters/weights resolved with a collection).

import types
import uuid

import httpx
import pytest

from backend.context import CONTEXT
from tests.units.api.conftest import make_collection_orm

# describe_stages stub with a chunk_strategy group so the create_collection pipeline overlay resolves.
_STAGES = {
    "stages": [
        {
            "id": "s4", "groups": [
                {
                    "key": "chunk.split_method", "kind": "single", "capability": "chunk_strategy",
                    "providers": [
                        {"id": "token_budget", "available": True, "selectable": True, "default": True,
                         "params": [{"name": "max_tokens", "type": "int", "default": 512, "min": 64, "max": 4096}]},
                        {"id": "semantic", "available": False, "selectable": True, "params": []},
                    ],
                },
            ],
        },
    ],
}


def _field(name: str, **kw: object) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        field_name=name, field_type=kw.get("type", "string"),
        filterable=kw.get("filterable", False), semantic=kw.get("semantic", False),
        lexical=kw.get("lexical", False), enum_values=kw.get("enum_values"),
        required=kw.get("required", False), is_system=kw.get("is_system", False),
    )


def _by_route(body: dict) -> dict:
    return {e["route_name"]: e for e in body["endpoints"]}


class TestDiscovery:
    @pytest.mark.asyncio
    async def test_returns_endpoints_and_components(self, client: httpx.AsyncClient) -> None:
        CONTEXT.registry.describe_stages.return_value = _STAGES
        r = await client.get("/api/v1/discovery")
        assert r.status_code == 200
        body = r.json()
        assert body["openapi_version"]
        assert body["endpoints"]
        assert "schemas" in body["components"]

    @pytest.mark.asyncio
    async def test_contracts_reference_components(self, client: httpx.AsyncClient) -> None:
        """Input/output contracts are $refs into the verbatim components (drift-proof, from OpenAPI)."""
        CONTEXT.registry.describe_stages.return_value = _STAGES
        body = (await client.get("/api/v1/discovery")).json()
        schemas = body["components"]["schemas"]
        cc = _by_route(body)["create_collection"]
        in_ref = cc["input"]["schema_ref"]
        assert in_ref.startswith("#/components/schemas/")
        assert in_ref.split("/")[-1] in schemas
        assert cc["output"]["status"] == "201"
        assert cc["output"]["schema_ref"].split("/")[-1] in schemas

    @pytest.mark.asyncio
    async def test_create_collection_pipeline_overlay(self, client: httpx.AsyncClient) -> None:
        CONTEXT.registry.describe_stages.return_value = _STAGES
        body = (await client.get("/api/v1/discovery")).json()
        cc = _by_route(body)["create_collection"]
        dfs = {d["field_path"]: d for d in cc["dynamic_fields"]}
        assert "pipeline.chunk.split_method" in dfs
        sm = dfs["pipeline.chunk.split_method"]
        ids = [c["id"] for c in sm["choices"]]
        assert ids == ["token_budget", "semantic"]
        tb = next(c for c in sm["choices"] if c["id"] == "token_budget")
        assert tb["fields"][0]["name"] == "max_tokens"

    @pytest.mark.asyncio
    async def test_search_filters_unresolved_without_collection(self, client: httpx.AsyncClient) -> None:
        CONTEXT.registry.describe_stages.return_value = _STAGES
        body = (await client.get("/api/v1/discovery")).json()
        sc = _by_route(body)["search_collection"]
        dfs = {d["field_path"]: d for d in sc["dynamic_fields"]}
        assert dfs["filters"]["resolved"] is False
        assert dfs["weights"]["resolved"] is False

    @pytest.mark.asyncio
    async def test_overlay_keys_bind_to_real_endpoints(self, client: httpx.AsyncClient) -> None:
        """Every overlay route key must match a real endpoint in the live app (drift guard)."""
        from backend.routers.discovery.overlays import OVERLAYS
        CONTEXT.registry.describe_stages.return_value = _STAGES
        body = (await client.get("/api/v1/discovery")).json()
        route_names = {e["route_name"] for e in body["endpoints"]}
        assert set(OVERLAYS).issubset(route_names)

    @pytest.mark.asyncio
    async def test_search_filters_resolved_with_collection(self, client: httpx.AsyncClient) -> None:
        CONTEXT.registry.describe_stages.return_value = _STAGES
        col = make_collection_orm(metadata_fields=[
            _field("dossier", filterable=True, semantic=True),
            _field("statut", type="enum", filterable=True, enum_values=["a", "b"]),
        ])
        CONTEXT.collection_repo.get_by_id.return_value = col
        cid = str(uuid.uuid4())
        body = (await client.get(f"/api/v1/discovery?collection_id={cid}")).json()
        assert body["collection_id"] == cid
        sc = _by_route(body)["search_collection"]
        filters = {d["field_path"]: d for d in sc["dynamic_fields"]}["filters"]
        assert filters["resolved"] is True
        assert {c["id"] for c in filters["choices"]} == {"dossier", "statut"}
