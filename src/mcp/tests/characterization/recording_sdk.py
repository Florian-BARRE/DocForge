# ====== Code Summary ======
# Test support for the MCP characterization suite: a stand-in for docforge_sdk.AsyncClient that
# records every `sdk.<resource>.<method>(...)` call a tool makes (resource, method, positional and
# keyword arguments, in order) and serialises it to plain JSON, so a golden file can pin exactly
# which SDK method each MCP tool calls and the request it builds. The stub never touches the
# network. Unless a test scripts a return value for a method, the call ends the tool run with a
# private sentinel exception: the golden records the call, and what a tool does with the response
# is out of this suite's scope (the response-shaping unit tests cover it).

from __future__ import annotations

# ====== Standard Library Imports ======
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from pydantic import BaseModel


class StubSdkCallRecorded(Exception):  # noqa: N818 - a control-flow sentinel, not an error
    """Raised by the stub after an unscripted SDK call: the call is recorded, the tool run ends."""


def to_plain(value: Any) -> Any:
    """
    Serialise an SDK call argument to deterministic, JSON-able data.

    A pydantic model keeps its class name and only the fields the tool set explicitly (so the
    golden pins what the tool shaped, not the SDK's defaults); bytes are summarised by size and
    digest; paths, datetimes and the `...` sentinel get an explicit tag so they cannot be confused
    with a plain string.

    Args:
        value (Any): One positional or keyword argument handed to an SDK method.

    Returns:
        Any: Plain dicts, lists and scalars.
    """
    if isinstance(value, BaseModel):
        return {
            "$model": type(value).__name__,
            "set": value.model_dump(mode="json", by_alias=True, exclude_unset=True),
        }
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_plain(item) for item in value]
    if isinstance(value, bytes):
        return {"$bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Path):
        return {"$path": str(value)}
    if isinstance(value, datetime | date):
        return {"$datetime": value.isoformat()}
    if value is ...:
        return {"$sentinel": "ellipsis"}
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"cannot serialise a {type(value).__name__} SDK argument for a golden")


@dataclass
class RecordedCall:
    """One SDK call a tool made."""

    call: str
    args: list[Any]
    kwargs: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        """The call as golden data (keyword arguments sorted by name)."""
        return {
            "call": self.call,
            "args": self.args,
            "kwargs": {key: self.kwargs[key] for key in sorted(self.kwargs)},
        }


@dataclass
class _Resource:
    """`sdk.<name>`: any method called on it is recorded on the owning stub."""

    stub: RecordingSdk
    name: str

    def __getattr__(self, method: str) -> Any:
        if method.startswith("_"):
            raise AttributeError(method)
        call_name = f"{self.name}.{method}"

        async def record(*args: Any, **kwargs: Any) -> Any:
            self.stub.calls.append(
                RecordedCall(
                    call=call_name,
                    args=[to_plain(arg) for arg in args],
                    kwargs={key: to_plain(value) for key, value in kwargs.items()},
                )
            )
            scripted = self.stub.returns.get(call_name)
            if scripted:
                return scripted.pop(0)
            raise StubSdkCallRecorded(call_name)

        return record


@dataclass
class RecordingSdk:
    """A recording stand-in for `AsyncClient` (see the module summary)."""

    # Calls in arrival order, across every resource.
    calls: list[RecordedCall] = field(default_factory=list)
    # Scripted return values per "resource.method", consumed in order; absent = end the run.
    returns: dict[str, list[Any]] = field(default_factory=dict)

    def __getattr__(self, resource: str) -> _Resource:
        if resource.startswith("_"):
            raise AttributeError(resource)
        return _Resource(self, resource)

    def as_client(self) -> AsyncClient:
        """The stub typed as the client the tool registrars expect."""
        return cast(AsyncClient, self)
