# ====== Code Summary ======
# The single serialisation choke point for tool results. FastMCP renders every non-str return with
# `to_json(indent=2)`, which on a hit-heavy payload is mostly whitespace an LLM pays tokens for.
# `compact_result` wraps every tool at registration (see ErrorTranslatingFastMCP.add_tool) so each
# structured return goes out as NON-indented JSON text; str / content-block returns pass through.

from __future__ import annotations

# ====== Standard Library Imports ======
import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

# ====== Third-Party Library Imports ======
import pydantic_core
from mcp.server.fastmcp.utilities.types import Audio, Image
from mcp.types import ContentBlock

AnyAsyncTool = Callable[..., Awaitable[Any]]


def compact_json(value: Any) -> str:
    """
    Serialise a value to compact JSON (no indentation, no padding after separators).

    Args:
        value (Any): A JSON-able value, pydantic model, or anything `pydantic_core` can encode.

    Returns:
        str: The compact JSON text (non-ASCII kept as-is; unknown types fall back to `str`).
    """
    return pydantic_core.to_json(value, fallback=str).decode()


def _compact_item(value: Any) -> Any:
    """Compact one return value, leaving text, None and MCP content blocks untouched."""
    if value is None or isinstance(value, str | ContentBlock | Image | Audio):
        return value
    return compact_json(value)


def compact_result(fn: AnyAsyncTool) -> AnyAsyncTool:
    """
    Wrap an async tool so its structured return is emitted as compact JSON text.

    A list/tuple return keeps FastMCP's one-content-block-per-item shape; only each item is
    compacted.

    Args:
        fn (AnyAsyncTool): The tool function to wrap.

    Returns:
        AnyAsyncTool: The wrapped function (`functools.wraps` keeps its signature introspectable).
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = await fn(*args, **kwargs)
        if isinstance(result, list | tuple):
            return [_compact_item(item) for item in result]
        return _compact_item(result)

    # The wrapper returns compact TEXT, so it must not advertise the wrapped tool's return type:
    # FastMCP reads `inspect.signature(fn, eval_str=True)` — which FOLLOWS `__wrapped__` — to build an
    # output schema, then validates the returned string against it (a tool typed `-> SomeModel`
    # would fail). An explicit `__signature__` wins over `__wrapped__`; with a return of `Any` no
    # output schema is derived. Parameters are kept so argument validation is unchanged.
    try:
        signature = inspect.signature(fn, eval_str=True)
    except NameError:
        # An annotation that can't be resolved at module scope (e.g. a locally-defined type) —
        # keep the raw signature; only the return annotation matters here.
        signature = inspect.signature(fn)
    wrapper.__signature__ = signature.replace(return_annotation=Any)  # type: ignore[attr-defined]
    return wrapper


__all__ = ["compact_json", "compact_result"]
