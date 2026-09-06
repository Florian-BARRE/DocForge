"""GET /blobs/{hash} response-header hardening: an uploaded HTML/SVG/text original must never be
served in a way a browser can render as a live same-origin document (stored-XSS -> token theft). The
route serves inert types (PDF, raster images) inline but forces a download + sandbox on everything
else, and always forbids MIME sniffing. Handler is called directly with a full-access principal (the
autouse fixture forces auth off); the store is mocked."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _full_principal():
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    return AuthPrincipal(user=SimpleNamespace(is_active=True), key=None, is_full_access=True)


async def _one_chunk_stream():
    """A minimal async byte-stream standing in for the facade's bounded S3 windows."""
    yield b"bytes"


async def _get_blob(monkeypatch, *, mime: str):
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(stream_blob=AsyncMock(return_value=(_one_chunk_stream(), mime)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))
    return await get_blob(content_hash="deadbeef", principal=_full_principal())


@pytest.mark.parametrize("mime", ["text/html", "image/svg+xml", "text/plain", "application/zip"])
async def test_unsafe_types_are_forced_download_and_sandboxed(
    fastapi_app, monkeypatch, mime
) -> None:
    response = await _get_blob(monkeypatch, mime=mime)

    assert response.headers["content-disposition"] == "attachment"
    assert response.headers["content-security-policy"] == "sandbox"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("mime", ["application/pdf", "image/png", "image/jpeg", "image/webp"])
async def test_inert_types_render_inline_but_still_nosniff(fastapi_app, monkeypatch, mime) -> None:
    response = await _get_blob(monkeypatch, mime=mime)

    # Page renders / figure crops / the PDF preview must stay inline (no attachment, no sandbox)...
    assert "content-disposition" not in response.headers
    assert "content-security-policy" not in response.headers
    # ...but MIME sniffing is forbidden on every blob regardless.
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.media_type == mime
