# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_capabilities.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous deployment discovery resource: the blocking shell over the shared
# ``_CapabilitiesSpecs`` builders.

# ====== Local Project Imports ======
from ...models.capabilities import CapabilitiesResponse
from .._base import SyncResource
from .specs import _CapabilitiesSpecs


class SyncCapabilities(SyncResource, _CapabilitiesSpecs):
    """Synchronous deployment discovery."""

    def capabilities(self) -> CapabilitiesResponse:
        """
        Discover what this deployment can do right now.

        Returns:
            CapabilitiesResponse: Version, auth state, GPU presence, the service list and the matrix.
        """
        return self._transport.request_bare(self._describe_spec(), CapabilitiesResponse)
