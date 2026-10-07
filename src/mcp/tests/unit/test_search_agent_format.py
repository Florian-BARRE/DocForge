# ====== Code Summary ======
# Wave B3 (agent UX): search_collection's agent-default projection, text rendering, compact json
# format, and the compact-JSON mechanism applied to every other tool. Calls go through real FastMCP
# dispatch (`mcp.call_tool`).

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import CollectionModel, SearchResponse
from pydantic import BaseModel

# ====== Internal Project Imports ======
from libs.server import build_mcp
from libs.tools.search_rendering import AGENT_RETURN_FIELDS


class TypedOut(BaseModel):
    """A module-level typed tool return, resolvable like a production tool's annotation."""

    a: int


CID = "11111111-1111-1111-1111-111111111111"

_PAYLOAD: dict[str, Any] = {
    "query": "intro",
    "hits": [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "document_title": "Annual Report",
            "page_number": 5,
            "heading_path": ["Part 1", "Introduction"],
            "score": 0.9567,
            "metadata": {"topic": "billing", "tags": ["a", "b"]},
            "text": "Hello world.",
        },
        {"chunk_id": "c2", "document_id": "d2", "text": "Bare hit."},
    ],
    "hints": [
        {
            "field": "topic",
            "value": "bilng",
            "message": "No doc has topic=bilng",
            "suggestions": ["billing"],
        }
    ],
}


def _server(payload: dict[str, Any] = _PAYLOAD) -> tuple[Any, AsyncMock]:
    sdk = AsyncClient("http://localhost:8000")
    search = AsyncMock(return_value=SearchResponse.model_validate(payload))
    sdk.search.search = search  # type: ignore[method-assign]
    return build_mcp(sdk), search


async def _text(mcp: Any, args: dict[str, Any]) -> str:
    content = await mcp.call_tool(
        "search_collection", {"collection_id": CID, "query": "intro", **args}
    )
    return str(content[0].text)


async def test_text_format_renders_header_citation_hints_and_no_geometry() -> None:
    mcp, _ = _server()
    out = await _text(mcp, {})
    lines = out.split("\n")
    assert lines[0] == '2 hits for "intro"'
    assert lines[1] == (
        "[1] Annual Report | p.5 | Part 1 > Introduction | score 0.96 | doc d1 | chunk c1"
    )
    assert lines[2] == "meta: topic=billing; tags=a,b"
    assert lines[3] == "Hello world."
    # A projected hit renders only what it carries (no title/score/page placeholders).
    assert lines[4] == "[2] doc d2 | chunk c2"
    assert lines[5] == "Bare hit."
    assert lines[-1] == "Hint: No doc has topic=bilng"
    assert "bbox" not in out and "block_locations" not in out


async def test_default_return_fields_applied_and_override_respected() -> None:
    mcp, search = _server()
    await _text(mcp, {})
    assert search.call_args.args[1].return_fields == AGENT_RETURN_FIELDS
    assert "bbox" not in AGENT_RETURN_FIELDS and "block_locations" not in AGENT_RETURN_FIELDS
    await _text(mcp, {"return_fields": ["text", "block_locations"]})
    assert search.call_args.args[1].return_fields == ["text", "block_locations"]


async def test_grouping_params_forwarded() -> None:
    mcp, search = _server()
    await _text(mcp, {"group_by": "document", "max_per_document": 2})
    request = search.call_args.args[1]
    assert request.group_by == "document" and request.max_per_document == 2
    await _text(mcp, {})
    request = search.call_args.args[1]
    assert request.group_by is None and "max_per_document" not in request.model_fields_set


async def test_json_format_is_compact_and_only_what_was_sent() -> None:
    mcp, _ = _server()
    out = await _text(mcp, {"format": "json"})
    assert "\n" not in out and ": " not in out.replace('"query":"intro"', "")
    data = json.loads(out)
    assert data["hits"][1] == {"chunk_id": "c2", "document_id": "d2", "text": "Bare hit."}
    assert "cost" not in data and "debug_info" not in data


async def test_every_structured_tool_returns_compact_json() -> None:
    sdk = AsyncClient("http://localhost:8000")
    collection = CollectionModel.model_validate(
        {
            "id": CID,
            "name": "docs",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1,
            "needs_reindex": False,
            "pipeline": {},
            "search": {},
        }
    )
    sdk.collections.get = AsyncMock(return_value=collection)  # type: ignore[method-assign]
    mcp = build_mcp(sdk)
    content: Any = await mcp.call_tool("get_collection", {"collection_id": CID})
    text = str(content[0].text)
    assert "\n" not in text and json.loads(text)["name"] == "docs"


async def test_debug_note_only_for_non_routine_diagnostics() -> None:
    routine = {**_PAYLOAD, "debug_info": {"hit_count": 2, "grouping": {"by": "document"}}}
    degraded = {**_PAYLOAD, "debug_info": {"hit_count": 2, "rerank": "skipped"}}
    mcp, _ = _server(routine)
    assert "debug" not in (await _text(mcp, {})).split("\n")[0]
    mcp, _ = _server(degraded)
    assert (await _text(mcp, {})).split("\n")[0].endswith('(debug: {"rerank":"skipped"})')


def test_compact_wrapper_never_advertises_a_typed_return() -> None:
    """A tool typed `-> SomeModel` must not get an output schema it would then fail (it returns text)."""
    import inspect  # noqa: PLC0415

    from libs.compact_json import compact_result  # noqa: PLC0415

    async def typed_tool() -> TypedOut:
        return TypedOut(a=1)

    wrapped = compact_result(typed_tool)
    # inspect.signature follows __wrapped__ unless __signature__ is set — FastMCP uses it.
    assert inspect.signature(wrapped, eval_str=True).return_annotation is Any


def test_text_render_skips_empty_meta_line() -> None:
    """A hit whose metadata values are all null renders no dangling 'meta:' line."""
    from docforge_sdk.models import SearchHit  # noqa: PLC0415

    from libs.tools.search_rendering import SearchTextRenderer  # noqa: PLC0415

    hit = SearchHit(chunk_id="c1", document_id="d1", text="body", metadata={"topic": None})
    rendered = SearchTextRenderer().render(
        SearchResponse(query="q", hits=[hit], score_kind="fused", hints=[])
    )
    assert "meta:" not in rendered


async def test_typed_return_tool_still_callable_through_the_server() -> None:
    """End to end: a tool typed `-> Model` registered on the real server returns compact JSON
    instead of failing FastMCP's output-schema validation against the compacted string."""
    from libs.error_translation import ErrorTranslatingFastMCP  # noqa: PLC0415

    server = ErrorTranslatingFastMCP(name="t")

    @server.tool()
    async def typed() -> TypedOut:
        return TypedOut(a=1)

    content = await server.call_tool("typed", {})
    blocks: Any = content[0] if isinstance(content, tuple) else content
    assert json.loads(blocks[0].text) == {"a": 1}
