# ---------------------- Capabilities composition service ---------------------- #
from .service import CapabilitiesService

# ---------------------- Sidecar reachability probe ---------------------- #
from .probe import ProbeResult, SidecarProbe

# ---------------------- Requirement tables (the one place kinds→sidecar) ---------------------- #
from .requirements import (
    FAMILY_MAP,
    SIDECARS,
    STORES,
    CapabilityRequirements,
    SidecarSpec,
    StoreSpec,
)

# ---------------------- API response contract ---------------------- #
from .models import CapabilitiesResponse, CapabilityMatrix, ServiceInfo

# ------------------- Public API ------------------- #
__all__ = [
    "CapabilitiesService",
    "ProbeResult",
    "SidecarProbe",
    "FAMILY_MAP",
    "SIDECARS",
    "STORES",
    "CapabilityRequirements",
    "SidecarSpec",
    "StoreSpec",
    "CapabilitiesResponse",
    "CapabilityMatrix",
    "ServiceInfo",
]
