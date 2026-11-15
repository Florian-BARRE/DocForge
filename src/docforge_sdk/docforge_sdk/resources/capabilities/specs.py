# ====== Code Summary ======
# The capabilities (deployment discovery) resource. Like /health, GET /capabilities lives at the BARE
# origin (outside /api/v1), so both shells route through the transport's request_bare helper rather
# than the versioned request. All URL logic lives once in the pure _CapabilitiesSpecs mixin; the
# async/sync shells differ only by await.

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from .._base import _ResourceMixin


class _CapabilitiesSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the capabilities endpoint — the single source of URL logic."""

    _CAPABILITIES_PATH = "/capabilities"

    def _describe_spec(self) -> RequestSpec:
        """
        Build the spec for the deployment discovery call.

        Returns:
            RequestSpec: A GET on the bare-root ``/capabilities`` route (outside ``/api/v1``).
        """
        return RequestSpec("GET", self._CAPABILITIES_PATH)
