# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_health.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous liveness probe resource: the blocking shell over the shared ``_HealthSpecs``
# builders.

# ====== Local Project Imports ======
from ...models.health import HealthStatus
from .._base import SyncResource
from .specs import _HealthSpecs


class SyncHealth(SyncResource, _HealthSpecs):
    """Synchronous liveness probe."""

    def ping(self) -> HealthStatus:
        """
        Probe the API's liveness.

        Returns:
            HealthStatus: The status payload (``status == "ok"`` when serving).
        """
        return self._transport.request_bare(self._ping_spec(), HealthStatus)
