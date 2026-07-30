# ====== Code Summary ======
# Base classes for resource groups. A resource holds only a reference to its transport; the async and
# sync bases exist so a resource can bind to the matching transport type while sharing the pure
# spec-building logic contributed by per-resource mixins (e.g. _AuthSpecs).

# ====== Local Project Imports ======
from .._transport import AsyncTransport, SyncTransport


class _ResourceMixin:
    """
    Marker base for the pure spec-builder mixins.

    Spec-builder mixins carry no state and no I/O — only methods returning ``RequestSpec`` — so the
    async and sync resources can share them verbatim.
    """


class AsyncResource:
    """Base for asynchronous resource groups; holds the async transport."""

    def __init__(self, transport: AsyncTransport) -> None:
        """
        Bind the resource to its async transport.

        Args:
            transport (AsyncTransport): The transport used to execute this resource's requests.
        """
        self._transport = transport


class SyncResource:
    """Base for synchronous resource groups; holds the sync transport."""

    def __init__(self, transport: SyncTransport) -> None:
        """
        Bind the resource to its sync transport.

        Args:
            transport (SyncTransport): The transport used to execute this resource's requests.
        """
        self._transport = transport


__all__ = ["_ResourceMixin", "AsyncResource", "SyncResource"]
