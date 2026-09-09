"""The Gotenberg converter's optional HTTP basic auth for a REMOTE instance.

A collection may point its converter at a remote Gotenberg protected by basic auth (username +
password stored per-collection). These tests pin that the node attaches an ``httpx.BasicAuth`` to
BOTH HTTP touchpoints (_convert office route + _preview chromium route) when both credentials are
set, and attaches NO auth when they are empty (the in-stack service, unchanged). Everything is
offline: the node's httpx client is monkeypatched, so no live Gotenberg is needed.
"""

import asyncio

import httpx
import pytest

from shared_libs.pipelines.ingest.nodes.intake.converter.gotenberg.config import (
    ConverterGotenbergConfig,
)
from shared_libs.pipelines.ingest.nodes.intake.converter.gotenberg.core import (
    ConverterGotenbergNode,
)
from shared_libs.public_models import SourceDocument, SourceProbe


class _FakeResponse:
    """A stand-in httpx.Response carrying canned PDF bytes."""

    content = b"%PDF-1.4 fake"

    def raise_for_status(self) -> None:
        return None


def _fake_async_client(*, captured: dict):
    """An httpx.AsyncClient stand-in that records the ``auth`` it was built with."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["auth"] = kwargs.get("auth")

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
            return _FakeResponse()

    return _Client


def _office_source() -> tuple[SourceDocument, SourceProbe]:
    source = SourceDocument(filename="report.docx", content=b"docx-bytes", metadata={})
    probe = SourceProbe(
        format="docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size=len(b"docx-bytes"),
    )
    return source, probe


def _html_source() -> tuple[SourceDocument, SourceProbe]:
    source = SourceDocument(filename="page.html", content=b"<html></html>", metadata={})
    probe = SourceProbe(format="html", mime_type="text/html", file_size=len(b"<html></html>"))
    return source, probe


# ==================== _convert (office route) ====================


def test_convert_attaches_basic_auth_when_credentials_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """A remote Gotenberg with username+password → the office POST carries httpx.BasicAuth."""
    captured: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured=captured))
    node = ConverterGotenbergNode(
        id="c",
        config=ConverterGotenbergConfig(
            base_url="https://gotenberg.remote:3000", username="forge", password="s3cr3t"
        ),
    )
    source, probe = _office_source()
    asyncio.run(node._convert(source, probe))
    assert isinstance(captured["auth"], httpx.BasicAuth)


def test_convert_sends_no_auth_when_credentials_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """The in-stack Gotenberg (no username/password) → no auth is attached (unchanged behaviour)."""
    captured: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured=captured))
    node = ConverterGotenbergNode(
        id="c", config=ConverterGotenbergConfig(base_url="http://gotenberg:3000")
    )
    source, probe = _office_source()
    asyncio.run(node._convert(source, probe))
    assert captured["auth"] is None


def test_convert_sends_no_auth_when_only_username_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth needs BOTH fields — a username alone (no password) attaches nothing."""
    captured: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured=captured))
    node = ConverterGotenbergNode(
        id="c",
        config=ConverterGotenbergConfig(base_url="http://gotenberg:3000", username="forge"),
    )
    source, probe = _office_source()
    asyncio.run(node._convert(source, probe))
    assert captured["auth"] is None


# ==================== _preview (chromium route) ====================


def test_preview_attaches_basic_auth_when_credentials_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The view-only html/md preview POST carries the same basic auth as the office route."""
    captured: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured=captured))
    node = ConverterGotenbergNode(
        id="c",
        config=ConverterGotenbergConfig(
            base_url="https://gotenberg.remote:3000", username="forge", password="s3cr3t"
        ),
    )
    source, probe = _html_source()
    asyncio.run(node._preview(source, probe))
    assert isinstance(captured["auth"], httpx.BasicAuth)


def test_preview_sends_no_auth_when_credentials_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """The in-stack preview render attaches no auth (unchanged)."""
    captured: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured=captured))
    node = ConverterGotenbergNode(
        id="c", config=ConverterGotenbergConfig(base_url="http://gotenberg:3000")
    )
    source, probe = _html_source()
    asyncio.run(node._preview(source, probe))
    assert captured["auth"] is None
