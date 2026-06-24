# ====== Code Summary ======
# Unit tests for the @auto_handle_errors decorator.
# Verifies that HTTPExceptions pass through, unexpected exceptions become 500s,
# and both async and sync handlers are covered.

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors


class TestAutoHandleErrors:
    """Tests for the @auto_handle_errors route decorator."""

    @pytest.fixture(autouse=True)
    def mock_logger(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Suppress real logging in all tests."""
        logger = MagicMock()
        monkeypatch.setattr(CONTEXT, "logger", logger, raising=False)
        monkeypatch.setattr(
            CONTEXT,
            "RUNTIME_CONFIG",
            MagicMock(FASTAPI_DEBUG_MODE=False),
            raising=False,
        )
        return logger

    # ─── Async handler tests ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_async_success_returns_value(self) -> None:
        """Decorated async function returns its value normally when no exception occurs."""

        @auto_handle_errors
        async def handler() -> str:
            return "ok"

        assert await handler() == "ok"

    @pytest.mark.asyncio
    async def test_async_http_exception_reraises(self) -> None:
        """HTTPException is re-raised as-is without being wrapped in a 500."""

        @auto_handle_errors
        async def handler():
            raise HTTPException(status_code=404, detail="not found")

        with pytest.raises(HTTPException) as exc_info:
            await handler()
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_async_unexpected_exception_becomes_500(self) -> None:
        """Any non-HTTP exception is caught and re-raised as a 500 HTTPException."""

        @auto_handle_errors
        async def handler():
            raise ValueError("database exploded")

        with pytest.raises(HTTPException) as exc_info:
            await handler()
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_async_500_detail_has_error_key(self, mock_logger: MagicMock) -> None:
        """The 500 response detail dict has an 'error' key."""

        @auto_handle_errors
        async def handler():
            raise RuntimeError("oops")

        with pytest.raises(HTTPException) as exc_info:
            await handler()
        assert "error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_async_exception_is_logged(self, mock_logger: MagicMock) -> None:
        """Unexpected exceptions are logged at ERROR level."""

        @auto_handle_errors
        async def handler():
            raise KeyError("missing key")

        with pytest.raises(HTTPException):
            await handler()
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_http_exception_not_logged_as_error(self, mock_logger: MagicMock) -> None:
        """HTTPExceptions are not logged as errors (they are expected application errors)."""

        @auto_handle_errors
        async def handler():
            raise HTTPException(status_code=422, detail="bad input")

        with pytest.raises(HTTPException):
            await handler()
        mock_logger.error.assert_not_called()

    # ─── Sync handler tests ──────────────────────────────────────────────────

    def test_sync_success_returns_value(self) -> None:
        """Decorated sync function returns its value normally."""

        @auto_handle_errors
        def handler() -> int:
            return 42

        assert handler() == 42

    def test_sync_http_exception_reraises(self) -> None:
        """HTTPException from a sync handler is re-raised unchanged."""

        @auto_handle_errors
        def handler():
            raise HTTPException(status_code=403, detail="forbidden")

        with pytest.raises(HTTPException) as exc_info:
            handler()
        assert exc_info.value.status_code == 403

    def test_sync_unexpected_exception_becomes_500(self) -> None:
        """Unexpected sync exception becomes HTTP 500."""

        @auto_handle_errors
        def handler():
            raise ZeroDivisionError("math error")

        with pytest.raises(HTTPException) as exc_info:
            handler()
        assert exc_info.value.status_code == 500

    # ─── Debug mode ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_debug_mode_includes_traceback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In debug mode, the 500 detail includes 'traceback' and 'function' keys."""
        monkeypatch.setattr(
            CONTEXT,
            "RUNTIME_CONFIG",
            MagicMock(FASTAPI_DEBUG_MODE=True),
            raising=False,
        )

        @auto_handle_errors
        async def handler():
            raise RuntimeError("debug error")

        with pytest.raises(HTTPException) as exc_info:
            await handler()
        detail = exc_info.value.detail
        assert "traceback" in detail
        assert "function" in detail

    @pytest.mark.asyncio
    async def test_prod_mode_hides_traceback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production mode, the 500 detail must NOT include traceback or function."""
        monkeypatch.setattr(
            CONTEXT,
            "RUNTIME_CONFIG",
            MagicMock(FASTAPI_DEBUG_MODE=False),
            raising=False,
        )

        @auto_handle_errors
        async def handler():
            raise RuntimeError("prod error")

        with pytest.raises(HTTPException) as exc_info:
            await handler()
        detail = exc_info.value.detail
        assert "traceback" not in detail
        assert "function" not in detail
        assert "error" in detail
