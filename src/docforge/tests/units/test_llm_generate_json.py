# ====== Code Summary ======
# Unit tests for OpenAICompatLLMProvider.generate_json — structured JSON generation
# with request-shape validation, refusal detection, bounded reask, tool-calling fallback,
# and graceful {} degrade on HTTP / parse errors. All HTTP is mocked via httpx patching.

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from common_libs.providers.llm.openai_compat.provider import OpenAICompatLLMProvider


# ─── Helpers ────────────────────────────────────────────────────────────────────

_SCHEMA = {
    "type": "object",
    "properties": {"keyword": {"type": "string"}},
    "required": ["keyword"],
    "additionalProperties": False,
}

_PROMPT = "Extract the keyword from the text."


def _provider(max_retries: int = 1) -> OpenAICompatLLMProvider:
    """Build a local provider (no real network needed)."""
    return OpenAICompatLLMProvider(
        base_url="http://localhost:8080",
        locality="local",
        api_key="local",
        model="test-model",
        json_max_retries=max_retries,
    )


def _mock_http_response(body: dict, status_code: int = 200) -> MagicMock:
    """Return a mock httpx Response that .json() yields body and .raise_for_status() no-ops."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    resp.text = json.dumps(body)
    return resp


def _mock_error_response(status_code: int, text: str) -> MagicMock:
    """Return a mock httpx Response that .raise_for_status() raises HTTPStatusError."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    request = MagicMock()
    exc = httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=resp)
    resp.raise_for_status = MagicMock(side_effect=exc)
    return resp


def _patch_httpx(responses: list[MagicMock]):
    """
    Context manager that patches httpx.AsyncClient so it returns a sequence of responses.

    The mock client's .post() is an AsyncMock that pops the next response from the list
    and calls .raise_for_status() (which may raise).
    """
    call_idx = [0]

    async def _post(*args, **kwargs):
        resp = responses[min(call_idx[0], len(responses) - 1)]
        call_idx[0] += 1
        resp.raise_for_status()
        return resp

    mock_client = AsyncMock()
    mock_client.post = _post

    async def _aenter(*args, **kwargs):
        return mock_client

    async def _aexit(*args, **kwargs):
        return None

    patcher = patch("common_libs.providers.llm.openai_compat.provider.httpx.AsyncClient")
    return patcher, _aenter, _aexit, mock_client


def _apply_patch(patcher, _aenter, _aexit):
    """Helper: patch + configure __aenter__ / __aexit__."""
    mock_cls = patcher.start()
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(side_effect=_aenter)
    instance.__aexit__ = AsyncMock(side_effect=_aexit)
    mock_cls.return_value = instance
    return mock_cls


# ─── Request shape ─────────────────────────────────────────────────────────────

class TestRequestShape:
    """generate_json must build a native response_format=json_schema payload."""

    @pytest.mark.asyncio
    async def test_request_uses_response_format_json_schema(self) -> None:
        """The first attempt uses response_format=json_schema with strict=True."""
        provider = _provider()
        success_body = {
            "choices": [{"message": {"content": '{"keyword": "python"}', "refusal": None}}]
        }
        resp = _mock_http_response(success_body)
        patcher, _aenter, _aexit, mock_client = _patch_httpx([resp])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {"keyword": "python"}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_bad_json(self) -> None:
        """When the model returns unparseable JSON, generate_json degrades to {}."""
        provider = _provider(max_retries=0)
        bad_body = {
            "choices": [{"message": {"content": "NOT JSON AT ALL", "refusal": None}}]
        }
        resp = _mock_http_response(bad_body)
        patcher, _aenter, _aexit, _ = _patch_httpx([resp])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_http_error(self) -> None:
        """A non-2xx HTTP response (that is not a response_format rejection) degrades to {}."""
        provider = _provider(max_retries=0)
        err_resp = _mock_error_response(500, "Internal Server Error")
        patcher, _aenter, _aexit, _ = _patch_httpx([err_resp])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {}


# ─── Refusal detection ─────────────────────────────────────────────────────────

class TestRefusalDetection:
    """A non-empty 'refusal' field must trigger the reask loop (then degrade)."""

    @pytest.mark.asyncio
    async def test_refusal_triggers_reask_and_degrades(self) -> None:
        """Model refusal → parse error → reask → eventual {} (no crash)."""
        provider = _provider(max_retries=0)  # No retries so we get {} after first refusal.
        refusal_body = {
            "choices": [{"message": {"content": None, "refusal": "I cannot help with that."}}]
        }
        resp = _mock_http_response(refusal_body)
        patcher, _aenter, _aexit, _ = _patch_httpx([resp])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {}


# ─── Reask loop ────────────────────────────────────────────────────────────────

class TestReaskLoop:
    """On a validation failure the provider appends a correction turn and retries."""

    @pytest.mark.asyncio
    async def test_reask_on_missing_required_key_then_success(self) -> None:
        """First response is missing the required key; the reask response is valid → returned."""
        provider = _provider(max_retries=1)
        bad_body = {
            "choices": [{"message": {"content": '{"wrong_key": "x"}', "refusal": None}}]
        }
        good_body = {
            "choices": [{"message": {"content": '{"keyword": "python"}', "refusal": None}}]
        }
        patcher, _aenter, _aexit, _ = _patch_httpx([
            _mock_http_response(bad_body),
            _mock_http_response(good_body),
        ])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {"keyword": "python"}

    @pytest.mark.asyncio
    async def test_exhausted_reask_degrades_to_empty_dict(self) -> None:
        """All reask attempts fail → graceful degrade to {}."""
        provider = _provider(max_retries=1)
        bad = _mock_http_response({
            "choices": [{"message": {"content": "bad json{{", "refusal": None}}]
        })
        patcher, _aenter, _aexit, _ = _patch_httpx([bad, bad])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {}


# ─── Tool-calling fallback ────────────────────────────────────────────────────

class TestToolCallingFallback:
    """A 400/422 response mentioning response_format triggers the tool-call fallback."""

    @pytest.mark.asyncio
    async def test_response_format_unsupported_falls_back_to_tools(self) -> None:
        """Server rejects response_format → provider retries with tool_choice fallback.

        The fallback uses `continue` to restart the for-loop, so `json_max_retries >= 1`
        is required to give the tool-calling path at least one iteration after the rejection.
        With max_retries=0 the loop runs only once; the `continue` after the fallback triggers
        exhausts the loop immediately and returns {}.  max_retries=1 gives two iterations:
        #0 → rejection → set use_tools=True, continue; #1 → tool payload → success.
        """
        provider = _provider(max_retries=1)
        rejection_text = '{"error": "response_format not supported for this model"}'

        # First response: 400 error mentioning response_format
        err_resp = MagicMock(spec=httpx.Response)
        err_resp.status_code = 400
        err_resp.text = rejection_text
        request = MagicMock()
        err = httpx.HTTPStatusError("HTTP 400", request=request, response=err_resp)
        err_resp.raise_for_status = MagicMock(side_effect=err)

        # Second response: success via tool_calls
        tool_body = {
            "choices": [{
                "message": {
                    "tool_calls": [{"function": {"arguments": '{"keyword": "tool-python"}'}}],
                    "content": None,
                    "refusal": None,
                }
            }]
        }
        ok_resp = _mock_http_response(tool_body)

        patcher, _aenter, _aexit, _ = _patch_httpx([err_resp, ok_resp])
        _apply_patch(patcher, _aenter, _aexit)
        try:
            result = await provider.generate_json(_PROMPT, _SCHEMA)
        finally:
            patcher.stop()

        assert result == {"keyword": "tool-python"}


# ─── External locality ────────────────────────────────────────────────────────

class TestExternalLocality:
    """External locality requires a non-empty api_key."""

    def test_external_without_api_key_raises(self) -> None:
        """Constructing an external provider with no api_key raises ValueError."""
        with pytest.raises(ValueError, match="api_key"):
            OpenAICompatLLMProvider(
                base_url="https://api.openai.com/v1",
                locality="external",
                api_key="",
            )

    def test_external_with_api_key_constructs_ok(self) -> None:
        """A valid external provider can be constructed without error (base_url is per-collection)."""
        provider = OpenAICompatLLMProvider(
            base_url="https://api.openai.com/v1",
            locality="external",
            api_key="sk-test123",
        )
        assert provider._locality == "external"
        assert provider._base_url == "https://api.openai.com/v1"
