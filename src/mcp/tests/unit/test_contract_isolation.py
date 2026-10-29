# ====== Code Summary ======
# Guards the unit suite against tests/contract's fixtures: the contract server swaps scoped_sdk's
# AsyncClient for one wired to a fake API, and that swap must end with tests/contract, so a unit
# test run after it (`uv run pytest`) still builds real docforge_sdk clients.

from __future__ import annotations

# ====== Third-Party Library Imports ======
import docforge_sdk

# ====== Internal Project Imports ======
import libs.scoped_sdk as scoped_sdk_module


def test_scoped_sdk_builds_real_sdk_clients() -> None:
    """No contract fixture leaves its patched client class behind."""
    assert scoped_sdk_module.AsyncClient is docforge_sdk.AsyncClient
