# ====== Code Summary ======
# Contract test of the production client's case: an in-house chatbot on an OpenAI model, which
# talks MCP through the OpenAI Agents SDK's MCPServerStreamableHttp (a wrapper over the mcp Python
# client). Runs openai_agents_client.py with the real Agents SDK in a throwaway env
# (client_env.py), once on mcp 2.x (what `openai-agents` resolves to today: protocol 2026-07-28)
# and once on mcp 1.x (a chatbot locked before mcp 2.0: 2025-11-25), and asserts the exact HTTP
# exchange the server saw. Every version is pinned and the resolution frozen, so a new upstream
# release never changes the result. Marked slow (it resolves the Agents SDK; needs uv and the
# package index or uv's cache), still part of the default run so the CI exercises it; skipped,
# with the reason, when uv cannot reach the index.

from __future__ import annotations

# ====== Standard Library Imports ======
import os
import shutil
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from client_env import (
    MCP_1X_REQUIREMENT,
    MCP_2X_REQUIREMENT,
    build_client_env,
    run_client_script,
)
from conftest import IMAGE_BLOB_HASH, ContractServer, WireRecord

_CLIENT_SCRIPT = Path(__file__).with_name("openai_agents_client.py")
# Pinned so the run is reproducible; bump them to follow the Agents SDK the chatbot uses.
_AGENTS_REQUIREMENT = "openai-agents==0.24.0"

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None, reason="needs uv to build the client env"
)


def _run_client(server: ContractServer, mcp_requirement: str) -> dict[str, Any]:
    return run_client_script(
        [_AGENTS_REQUIREMENT, mcp_requirement],
        "agents.mcp",
        _CLIENT_SCRIPT,
        server.url,
        "chatbot-key",
        IMAGE_BLOB_HASH,
    )


def _assert_results(report: dict[str, Any], server: ContractServer) -> None:
    assert report["tool_count"] == 85
    assert report["ping"] == {
        "is_error": False,
        "content": [{"type": "text", "text": '{"status":"ok"}'}],
    }
    assert report["image"] == {
        "is_error": False,
        "content": [{"type": "image", "mime_type": "image/png"}],
    }
    assert report["missing"]["is_error"] is True
    assert "DocForge API error 404" in report["missing"]["content"][0]["text"]
    # Every call reached DocForge with the chatbot's own key.
    assert {auth for auth, _ in server.api.calls} == {"Bearer chatbot-key"}


def _assert_every_request_carries_the_bearer(wire: list[WireRecord]) -> None:
    for record in wire:
        assert record.headers.get("authorization") == "Bearer chatbot-key", record
        assert record.headers.get("accept") == "application/json, text/event-stream", record


def test_an_unreachable_package_index_skips_with_the_reason(tmp_path: Path) -> None:
    """Offline with an empty cache, building the client env skips instead of failing."""
    env = {**os.environ, "UV_CACHE_DIR": str(tmp_path), "UV_OFFLINE": "1"}
    with pytest.raises(pytest.skip.Exception, match="uv cannot reach the package index"):
        build_client_env([_AGENTS_REQUIREMENT, MCP_2X_REQUIREMENT], "agents.mcp", env=env)


@pytest.mark.slow
def test_agents_sdk_on_mcp_2x_discovers_2026_07_28(server: ContractServer) -> None:
    """
    mcp 2.x's Client(mode="auto"), which the Agents SDK uses on mcp 2, probes `server/discover`
    at 2026-07-28; the server (mcp 2.x) answers it, so there is no initialize handshake and every
    later request carries 2026-07-28. (On mcp 1.x the server refused the probe with a 400 and the
    client fell back to initialize at 2025-11-25.)
    """
    report = _run_client(server, MCP_2X_REQUIREMENT)
    assert report["mcp_version"] == "2.3.0"
    _assert_results(report, server)

    _assert_every_request_carries_the_bearer(server.wire)
    assert [r.rpc_method for r in server.wire] == [
        "server/discover",
        "tools/list",
        "tools/call",
        "tools/call",
        "tools/call",
    ]
    for record in server.wire:
        assert record.headers.get("mcp-protocol-version") == "2026-07-28", record
        assert record.status == 200, record


@pytest.mark.slow
def test_agents_sdk_on_mcp_1x_initializes_at_2025_11_25(server: ContractServer) -> None:
    """mcp 1.x's ClientSession, which the Agents SDK uses on mcp 1, goes straight to initialize."""
    report = _run_client(server, MCP_1X_REQUIREMENT)
    assert report["mcp_version"] == "1.29.1"
    _assert_results(report, server)

    _assert_every_request_carries_the_bearer(server.wire)
    initialize, *rest = server.wire
    assert (initialize.rpc_method, initialize.status) == ("initialize", 200)
    assert [r.rpc_method for r in rest] == [
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "tools/call",
        "tools/call",
    ]
    for record in rest:
        assert record.headers.get("mcp-protocol-version") == "2025-11-25", record
