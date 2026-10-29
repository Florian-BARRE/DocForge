# ====== Code Summary ======
# Contract test of the production client's case: an in-house chatbot on an OpenAI model, which
# talks MCP through the OpenAI Agents SDK's MCPServerStreamableHttp (a wrapper over the mcp Python
# client). Runs openai_agents_client.py with the real Agents SDK in a throwaway `uv run --with`
# environment, once on mcp 2.x (what `openai-agents` resolves to today) and once on mcp 1.x (a
# chatbot locked before mcp 2.0), and asserts the exact HTTP handshake the server saw.
# Marked slow (it resolves the Agents SDK; needs uv and the package index or uv's cache), still
# part of the default run so the CI exercises it.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from conftest import IMAGE_BLOB_HASH, ContractServer, WireRecord

_CLIENT_SCRIPT = Path(__file__).with_name("openai_agents_client.py")
# Pinned so the run is reproducible; bump it to follow the Agents SDK the chatbot uses.
_AGENTS_REQUIREMENT = "openai-agents==0.24.0"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv to build the client env"),
]


def _run_client(server: ContractServer, mcp_requirement: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--isolated",
            "--with",
            _AGENTS_REQUIREMENT,
            "--with",
            mcp_requirement,
            "python",
            "-I",
            str(_CLIENT_SCRIPT),
            server.url,
            "chatbot-key",
            IMAGE_BLOB_HASH,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    report: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    return report


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


def test_agents_sdk_on_mcp_2x_probes_discover_then_falls_back_to_2025_11_25(
    server: ContractServer,
) -> None:
    """
    mcp 2.x's Client(mode="auto"), which the Agents SDK uses on mcp 2, first probes
    `server/discover` at 2026-07-28; today's server refuses that version at the HTTP layer (400),
    and the client falls back to the initialize handshake at 2025-11-25.
    """
    report = _run_client(server, "mcp>=2,<3")
    assert report["mcp_version"].startswith("2.")
    _assert_results(report, server)

    _assert_every_request_carries_the_bearer(server.wire)
    probe, initialize, *rest = server.wire
    assert (probe.rpc_method, probe.headers.get("mcp-protocol-version"), probe.status) == (
        "server/discover",
        "2026-07-28",
        400,
    )
    assert (initialize.rpc_method, initialize.status) == ("initialize", 200)
    assert "mcp-protocol-version" not in initialize.headers
    assert [r.rpc_method for r in rest] == [
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "tools/call",
        "tools/call",
    ]
    for record in rest:
        assert record.headers.get("mcp-protocol-version") == "2025-11-25", record
        assert record.status in (200, 202), record


def test_agents_sdk_on_mcp_1x_initializes_at_2025_11_25(server: ContractServer) -> None:
    """mcp 1.x's ClientSession, which the Agents SDK uses on mcp 1, goes straight to initialize."""
    report = _run_client(server, "mcp>=1.29,<2")
    assert report["mcp_version"].startswith("1.")
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
