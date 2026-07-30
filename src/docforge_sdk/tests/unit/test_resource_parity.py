# ====== Code Summary ======
# The drift guard: AsyncAuth and SyncAuth must expose the SAME public method names and the SAME
# signatures (P2 relies on this to keep every future resource's async/sync pair in lockstep). Return
# annotations legitimately differ where one is awaitable, so only names + parameters are compared.

# ====== Standard Library Imports ======
import inspect

# ====== Local Project Imports ======
from docforge_sdk.resources.auth import AsyncAuth, SyncAuth


def _public_methods(cls: type) -> set[str]:
    """Return the names of a class's public (non-underscore) callables."""
    return {name for name in dir(cls) if not name.startswith("_") and callable(getattr(cls, name))}


def _parameters(cls: type, method: str) -> list[inspect.Parameter]:
    """Return the parameter objects of a method, ignoring the return annotation."""
    return list(inspect.signature(getattr(cls, method)).parameters.values())


def test_async_and_sync_expose_same_public_methods() -> None:
    assert _public_methods(AsyncAuth) == _public_methods(SyncAuth)


def test_async_and_sync_signatures_match() -> None:
    for method in _public_methods(AsyncAuth):
        assert _parameters(AsyncAuth, method) == _parameters(SyncAuth, method), method
