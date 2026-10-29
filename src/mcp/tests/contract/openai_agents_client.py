# ====== Code Summary ======
# Standalone client script (NOT a test module): drives docforge's MCP server the way an in-house
# chatbot built on the OpenAI Agents SDK does - `agents.mcp.MCPServerStreamableHttp` with the
# caller's DocForge key in `headers`, its documented connection pattern. test_openai_agents_client.py
# runs it in a throwaway `uv run --no-project --with openai-agents==...` environment (the Agents
# SDK is not a dependency of this project) and prints one JSON report on stdout.
#
# Usage: python openai_agents_client.py <mcp-url> <bearer-token> <image-blob-hash>

# ====== Standard Library Imports ======
import asyncio
import json
import sys
from importlib.metadata import version
from typing import Any

# ====== Third-Party Library Imports ======
from agents.mcp import MCPServerStreamableHttp


def _blocks(result: Any) -> list[dict[str, Any]]:
    """Each content block's type, plus its text or mime type (attribute names differ by mcp major)."""
    blocks = []
    for block in result.content:
        entry = {"type": block.type}
        if block.type == "text":
            entry["text"] = block.text
        elif block.type == "image":
            entry["mime_type"] = getattr(block, "mime_type", None) or block.mimeType
        blocks.append(entry)
    return blocks


def _is_error(result: Any) -> bool:
    return bool(getattr(result, "is_error", None) or getattr(result, "isError", None))


async def main(url: str, token: str, image_hash: str) -> dict[str, Any]:
    server = MCPServerStreamableHttp(
        name="docforge",
        params={"url": url, "headers": {"Authorization": f"Bearer {token}"}},
        cache_tools_list=True,
    )
    async with server:
        tools = await server.list_tools()
        ping = await server.call_tool("ping", {})
        image = await server.call_tool("get_blob", {"content_hash": image_hash})
        missing = await server.call_tool("get_document", {"document_id": "missing"})
    return {
        "agents_version": version("openai-agents"),
        "mcp_version": version("mcp"),
        "tool_count": len(tools),
        "ping": {"is_error": _is_error(ping), "content": _blocks(ping)},
        "image": {"is_error": _is_error(image), "content": _blocks(image)},
        "missing": {"is_error": _is_error(missing), "content": _blocks(missing)},
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(*sys.argv[1:4]))))
