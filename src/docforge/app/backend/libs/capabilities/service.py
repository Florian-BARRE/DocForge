# ====== Code Summary ======
# CapabilitiesService — assembles the deployment self-description served by GET /capabilities: the
# running version + auth state (static config reads), the infra stores + optional sidecars (the latter
# via the short-cached SidecarProbe), the derived GPU presence, and the per-family available-kinds
# matrix. The matrix is DECLARED (read live from the NodeRegistry palette) intersected with cached
# sidecar reachability — never a live per-request probe of the whole stack. It writes nothing and
# enqueues nothing; the ONE place that knows which sidecar a kind needs is requirements.py.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .models import CapabilitiesResponse, CapabilityMatrix, ServiceInfo
from .probe import ProbeResult, SidecarProbe
from .requirements import FAMILY_MAP, SIDECARS, STORES, CapabilityRequirements


class CapabilitiesService(LoggerClass):
    """Composes the deployment capability snapshot from static config, the registry and the probe."""

    def __init__(self, runtime_config: Any, probe: SidecarProbe) -> None:
        """
        Args:
            runtime_config (Any): The app ``RUNTIME_CONFIG`` — read for the version, auth flag and the
                sidecar/store URLs (each named by a spec's ``config_attr``).
            probe (SidecarProbe): The short-cached sidecar reachability probe.
        """
        LoggerClass.__init__(self)
        self._config = runtime_config
        self._probe = probe

    def __sidecar_targets(self) -> dict[str, str]:
        """Build ``sidecar name → base URL`` from the specs, reading each URL from RUNTIME_CONFIG."""
        # 1. Each spec names the RUNTIME_CONFIG attribute holding its /health base URL.
        return {
            sidecar.name: getattr(self._config, sidecar.config_attr) for sidecar in SIDECARS
        }

    def __service_rows(self, probes: dict[str, ProbeResult]) -> list[ServiceInfo]:
        """Assemble the ServiceInfo rows: probed sidecars first, then config-derived infra stores."""
        # 1. Sidecars — reachability + advertised device + what each unlocks, straight from the probe.
        rows: list[ServiceInfo] = [
            ServiceInfo(
                name=sidecar.name,
                role=sidecar.role,
                reachable=probes[sidecar.name].reachable,
                device=probes[sidecar.name].device,
                provides=list(sidecar.provides),
                detail=probes[sidecar.name].detail,
            )
            for sidecar in SIDECARS
        ]

        # 2. Infra stores — declared (configured) or not; never live-probed here (kept cheap).
        for store in STORES:
            configured = bool(getattr(self._config, store.config_attr, None))
            rows.append(
                ServiceInfo(
                    name=store.name,
                    role=store.role,
                    reachable=configured,
                    device=None,
                    provides=[],
                    detail="declared (not probed)" if configured else "not configured",
                )
            )
        return rows

    def __gpu_present(self, probes: dict[str, ProbeResult]) -> bool | None:
        """Derive GPU presence from reachable sidecars' advertised devices (None when unknown)."""
        # 1. Only reachable sidecars that actually advertise a device inform the verdict.
        devices = [r.device for r in probes.values() if r.reachable and r.device]
        if any(device == "cuda" for device in devices):
            return True
        if devices:
            return False
        return None

    def __matrix(self, reachable_sidecars: set[str]) -> CapabilityMatrix:
        """Build the per-family available-kinds matrix from the live palette + sidecar reachability."""
        # 1. Per family: the SELECTABLE registry kinds whose requirement is satisfied right now.
        available: dict[str, list[str]] = {}
        for field, family in FAMILY_MAP.items():
            available[field] = [
                card.kind
                for card in NodeRegistry.catalog(family)
                if CapabilityRequirements.is_available(f"{family}:{card.kind}", reachable_sidecars)
            ]
        return CapabilityMatrix(**available)

    async def describe(self) -> CapabilitiesResponse:
        """
        Build the full deployment capability snapshot.

        Returns:
            CapabilitiesResponse: Version, auth state, GPU presence, the service list and the matrix.
        """
        # 1. Cached reachability probe of every optional sidecar (cheap on a burst of calls).
        probes = await self._probe.probe(self.__sidecar_targets())
        reachable_sidecars = {name for name, result in probes.items() if result.reachable}

        # 2. Static config facts + derived signals + the palette∩reachability matrix.
        return CapabilitiesResponse(
            version=self._config.FASTAPI_APP_VERSION,
            auth_enabled=self._config.AUTH_ENABLED,
            gpu_present=self.__gpu_present(probes),
            services=self.__service_rows(probes),
            capabilities=self.__matrix(reachable_sidecars),
        )


__all__ = ["CapabilitiesService"]
