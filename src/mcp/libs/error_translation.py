# ====== Code Summary ======
# The single choke point that keeps every tool's error informative: a raw `docforge_sdk`
# `APIStatusError` reaching the LLM as-is carries only "API request failed with status 404" — the
# useful REST error body (e.g. "collection name already exists") never reaches the model, so it
# can't self-correct. Likewise, a bare pydantic `ValidationError` raised while a tool builds a typed
# SDK model from the LLM's plain-dict arguments (e.g. `FieldSpec(**field)`) would otherwise fall
# through to FastMCP's generic unhandled-exception path and lose its per-field detail.
# `ErrorTranslatingFastMCP` wraps every tool at registration time (the ONE place `@mcp.tool()`
# funnels through — `FastMCP.add_tool`) so no individual tool file needs its own try/except.

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
from pydantic import ValidationError

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


def _validation_error_message(exc: ValidationError) -> str:
    """
    Render a pydantic `ValidationError` into a message naming each offending field and what was
    wrong with it, instead of FastMCP's generic unhandled-exception path (which loses the
    per-field detail).

    The wrapper below applies this to EVERY `ValidationError` raised inside a tool call — which
    covers two distinct sources: a tool building a typed SDK REQUEST model from the LLM's plain
    dict at the tool boundary (e.g. `FieldSpec(**field)`, `SearchTarget(**target)`,
    `DocumentFilter(**filter)`, `KeyPermissions.model_validate(permissions)`,
    `CollectionSnippet(**snippet)`), AND — more rarely — the SDK parsing a RESPONSE body it didn't
    expect. The message deliberately says "argument or response field(s)" rather than assuming the
    caller's input was at fault, since this function cannot tell the two apart.

    Args:
        exc (ValidationError): The validation failure, from either source above.

    Returns:
        str: One line per invalid field: dotted location, message, and the value received.
    """
    lines = [
        f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']} "
        f"(got {error.get('input')!r})"
        for error in exc.errors()
    ]
    return "Invalid argument or response field(s):\n" + "\n".join(lines)


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
        except ValidationError as exc:
            raise ToolError(_validation_error_message(exc)) from exc

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
