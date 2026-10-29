# ====== Code Summary ======
# Standalone client script (NOT a test module): drives docforge's MCP server over streamable HTTP
# with the mcp 1.x Python client (`streamablehttp_client` + `ClientSession`), the way a client
# locked before mcp 2.0 does. test_http_wire.py runs it in a throwaway `uv run --no-project --with
# mcp==1.x` environment (this project locks mcp 2.x, and the two majors cannot share one env) and
# prints one JSON report on stdout, the same shape as the in-process mcp 2.x report.
#
# Usage: python mcp1_client.py <mcp-url> <image-blob-hash> <collection-id>
#
# mypy checks this project against mcp 2.x, whose client API differs (camelCase fields, renamed
# transport): this file targets mcp 1.x on purpose.
# mypy: ignore-errors

# ====== Standard Library Imports ======
import asyncio
import json
import sys
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

# ====== Third-Party Library Imports ======
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# streamablehttp_client is the 1.x name the OpenAI Agents SDK still calls on mcp 1.x; 1.29 flags it.
warnings.filterwarnings("ignore", category=DeprecationWarning)

WHOAMI_TOKENS = [f"key-{n}" for n in range(8)]


@asynccontextmanager
async def _session(url: str, token: str) -> AsyncIterator[ClientSession]:
    async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            yield session


def _result(result: Any) -> dict[str, Any]:
    """A tool result: its error flag, whether it carries structured content, and its blocks."""
    blocks = []
    for block in result.content:
        entry = {"type": block.type}
        if block.type == "text":
            entry["text"] = block.text
        elif block.type == "image":
            entry["mime_type"] = block.mimeType
            entry["data"] = block.data
        blocks.append(entry)
    return {
        "is_error": result.isError,
        "structured": result.structuredContent is not None,
        "content": blocks,
    }


async def _whoami(url: str, token: str) -> str:
    async with _session(url, token) as session:
        await session.initialize()
        result = await session.call_tool("whoami", {})
    collections: list[str] = json.loads(result.content[0].text)["collections"]
    return collections[0]


async def main(url: str, image_hash: str, collection_id: str) -> dict[str, Any]:
    async with _session(url, "key-a") as session:
        init = await session.initialize()
        await session.send_ping()
        tools = await session.list_tools()
        calls = {
            "ping": await session.call_tool("ping", {}),
            "search": await session.call_tool(
                "search_collection", {"collection_id": collection_id, "query": "intro"}
            ),
            "image": await session.call_tool("get_blob", {"content_hash": image_hash}),
            "missing": await session.call_tool("get_document", {"document_id": "missing"}),
            "bogus": await session.call_tool("ping", {"bogus": 1}),
        }
    whoami = await asyncio.gather(*(_whoami(url, token) for token in WHOAMI_TOKENS))
    return {
        "mcp_version": version("mcp"),
        "protocol_version": init.protocolVersion,
        "server_name": init.serverInfo.name,
        "server_version": init.serverInfo.version,
        "has_tools_capability": init.capabilities.tools is not None,
        "tool_count": len(tools.tools),
        "calls": {name: _result(result) for name, result in calls.items()},
        "whoami": {"tokens": WHOAMI_TOKENS, "seen": list(whoami)},
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(*sys.argv[1:4]))))
