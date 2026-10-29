# ====== Code Summary ======
# Unit tests for libs/sdk_logging.py: once route_sdk_logging() ran, the mcp SDK's own stdlib
# records (a tool call rejected on its arguments at INFO, a crashing tool at ERROR with its
# traceback) come out through loggerplusplus, once each, at their level and labelled with the
# SDK logger name — and no longer through the root handler the SDK installs. The tool results
# the client sees are unchanged.

from __future__ import annotations

# ====== Standard Library Imports ======
import logging
from collections.abc import Iterator
from typing import Any, cast

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient
from loggerplusplus import loggerplusplus
from mcp import Client

# ====== Internal Project Imports ======
from libs.scoped_sdk import ScopedSdk, ScopedSdkProvider
from libs.sdk_logging import SDK_LOGGER, route_sdk_logging
from libs.server import build_mcp

_SERVER_LOGGER = "mcp.server.mcpserver.server"


class _RootRecorder(logging.Handler):
    """Collects what reaches the root logger (where the SDK's own handler sits)."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def root_messages() -> Iterator[list[str]]:
    """Messages that reached the root logger during one test."""
    recorder = _RootRecorder()
    logging.getLogger().addHandler(recorder)
    try:
        yield recorder.messages
    finally:
        logging.getLogger().removeHandler(recorder)


@pytest.fixture
def sdk_records() -> Iterator[list[dict[str, Any]]]:
    """Route the SDK logging for one test and collect what reaches loggerplusplus."""
    sdk_logger = logging.getLogger(SDK_LOGGER)
    saved = (list(sdk_logger.handlers), sdk_logger.propagate, sdk_logger.level)
    records: list[dict[str, Any]] = []
    sink_id = loggerplusplus.add(lambda message: records.append(message.record), level="TRACE")
    try:
        route_sdk_logging()
        yield records
    finally:
        loggerplusplus.remove(sink_id)
        sdk_logger.handlers, sdk_logger.propagate = saved[0], saved[1]
        sdk_logger.setLevel(saved[2])


def _from_sdk(records: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    """The captured records whose message contains `text`."""
    return [record for record in records if text in record["message"]]


async def test_a_rejected_tool_call_is_logged_once_through_loggerplusplus_at_info(
    sdk_records: list[dict[str, Any]], root_messages: list[str]
) -> None:
    """The SDK's 'rejected arguments' record keeps its INFO level and is not printed twice."""
    mcp = build_mcp(AsyncClient("http://localhost:8000"))
    async with Client(mcp) as client:
        result = await client.call_tool("list_collections", {"unknown_argument": 1})

    assert result.is_error
    (record,) = _from_sdk(sdk_records, "rejected arguments")
    assert record["level"].name == "INFO"
    assert record["extra"]["identifier"] == _SERVER_LOGGER
    assert "'list_collections'" in record["message"]
    assert not root_messages, "the record also reached the root handler (printed twice)"


async def test_a_crashing_tool_is_logged_once_through_loggerplusplus_at_error(
    sdk_records: list[dict[str, Any]], root_messages: list[str]
) -> None:
    """An unexpected exception is logged at ERROR with its traceback; the client gets no detail."""
    # HTTP-mode provider with no bearer in context: the SDK lookup raises MissingBearerTokenError,
    # which no tool translates — a true crash for the SDK.
    provider = ScopedSdkProvider(
        "http://localhost:8000", timeout=1.0, fallback_token="", require_bearer=True
    )
    mcp = build_mcp(cast(AsyncClient, ScopedSdk(provider)))
    try:
        async with Client(mcp) as client:
            result = await client.call_tool("list_collections", {})
    finally:
        await provider.aclose()

    assert result.is_error
    (record,) = _from_sdk(sdk_records, "raised an unexpected exception")
    assert record["level"].name == "ERROR"
    assert record["exception"] is not None
    assert record["extra"]["identifier"] == _SERVER_LOGGER
    assert not root_messages, "the record also reached the root handler (printed twice)"


def test_route_sdk_logging_is_idempotent(sdk_records: list[dict[str, Any]]) -> None:
    """A second call replaces the handler instead of stacking a second one (no duplicates)."""
    route_sdk_logging()
    sdk_logger = logging.getLogger(SDK_LOGGER)
    assert len(sdk_logger.handlers) == 1
    assert sdk_logger.propagate is False
    logging.getLogger(_SERVER_LOGGER).info("probe")
    assert len(_from_sdk(sdk_records, "probe")) == 1
