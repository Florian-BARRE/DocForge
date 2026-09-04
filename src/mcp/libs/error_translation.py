# ====== Code Summary ======
# The single choke point that keeps every tool's API error informative: a raw `docforge_sdk`
# `APIStatusError` reaching the LLM as-is carries only "API request failed with status 404" — the
# useful REST error body (e.g. "collection name already exists") never reaches the model, so it
# can't self-correct. `ErrorTranslatingFastMCP` wraps every tool at registration time (the ONE
# place `@mcp.tool()` funnels through — `FastMCP.add_tool`) so no individual tool file needs its
# own try/except.

from __future__ import annotations

# ====== Standard Library Imports ======
import functools
from collections.abc import Awaitable, Callable
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import APIConnectionError, APIStatusError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import Icon, ToolAnnotations

AnyAsyncTool = Callable[..., Awaitable[Any]]


def _status_error_message(exc: APIStatusError) -> str:
    """
    Render an `APIStatusError` as a message carrying the API's own error detail.

    Args:
        exc (APIStatusError): The SDK exception raised for a 4xx/5xx response.

    Returns:
        str: The response body's `detail` field when the body is a dict shaped that way, else the
            raw decoded body (already JSON or plain text — never raw headers).
    """
    body = exc.body
    detail = body.get("detail") if isinstance(body, dict) and "detail" in body else body
    return f"DocForge API error {exc.status_code}: {detail}"


def translate_sdk_errors(fn: AnyAsyncTool) -> AnyAsyncTool:
    """
    Wrap an async tool function so a failed SDK call surfaces its response body to the LLM.

    Args:
        fn (AnyAsyncTool): The tool function to wrap.

    Returns:
        AnyAsyncTool: The wrapped function. `functools.wraps` keeps `__wrapped__` pointed at `fn`,
            so FastMCP's signature introspection (which follows it) still builds the correct
            argument model.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except APIStatusError as exc:
            raise ToolError(_status_error_message(exc)) from exc
        except APIConnectionError as exc:
            raise ToolError(f"DocForge API unreachable: {exc}") from exc

    return wrapper


class ErrorTranslatingFastMCP(FastMCP):
    """A `FastMCP` whose every registered tool has SDK API errors translated before they reach FastMCP's own generic exception handling."""

    def add_tool(
        self,
        fn: AnyAsyncTool,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
        icons: list[Icon] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> None:
        """Register `fn` wrapped by `translate_sdk_errors` — see `FastMCP.add_tool` for the args."""
        super().add_tool(
            translate_sdk_errors(fn),
            name=name,
            title=title,
            description=description,
            annotations=annotations,
            icons=icons,
            meta=meta,
            structured_output=structured_output,
        )


__all__ = ["ErrorTranslatingFastMCP", "translate_sdk_errors"]
