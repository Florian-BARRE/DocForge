# ====== Code Summary ======
# SidecarProbe — the short-cached reachability probe for the optional in-stack sidecars. It GETs each
# sidecar's /health with a SHORT timeout and memoizes the whole result map behind a small TTL, so a
# burst of GET /capabilities calls costs at most one probe round per TTL window (cheap + deterministic,
# never a live probe on every request). A non-deployed sidecar (its compose profile off) simply fails
# the probe and reads as unreachable — the endpoint degrades, it never errors. This is a liveness/
# reachability read only: it writes nothing and reaches only the URLs handed to it by the service.

# ====== Standard Library Imports ======
import asyncio
import time
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass


@dataclass(frozen=True)
class ProbeResult:
    """
    The outcome of one sidecar /health probe.

    Attributes:
        reachable (bool): True only when /health answered HTTP 200 (deployed AND ready).
        device (str | None): The device the sidecar advertised in its /health JSON (``"cuda"``/``"cpu"``),
            or None when the sidecar omits it or the probe failed.
        detail (str | None): A short note when not reachable (unreachable / not-ready), else None.
    """

    reachable: bool
    device: str | None
    detail: str | None


class SidecarProbe(LoggerClass):
    """Probes optional sidecars' /health with a short timeout and a small TTL cache over the results."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        cache_ttl_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Args:
            timeout_seconds (float): Per-probe HTTP timeout — short, so an unreachable sidecar fails fast.
            cache_ttl_seconds (float): How long a probe result map is reused before the next refresh.
            transport (httpx.AsyncBaseTransport | None): Optional injected transport (tests pass a
                ``httpx.MockTransport`` to assert the TTL cache without real network I/O).
        """
        LoggerClass.__init__(self)
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._transport = transport
        self._cache: dict[str, ProbeResult] | None = None
        self._cached_at: float = 0.0
        self._lock = asyncio.Lock()

    async def __probe_one(self, client: httpx.AsyncClient, name: str, base_url: str) -> ProbeResult:
        """
        Probe a single sidecar's /health (never raises — a failure is reported as unreachable).

        Args:
            client (httpx.AsyncClient): The shared client for this refresh round.
            name (str): The sidecar name (for logging).
            base_url (str): The sidecar's base URL; ``/health`` is appended.

        Returns:
            ProbeResult: Reachability, advertised device (if any) and a short note when not reachable.
        """
        # 1. A connect/timeout failure means the sidecar is simply not deployed — expected, not a bug.
        try:
            response = await client.get(f"{base_url.rstrip('/')}/health")
        except Exception as exc:  # noqa: BLE001 — the /capabilities contract is "degrade, never error":
            # ANY failure (HTTP error, DNS, a misconfigured/None base_url raising AttributeError, …)
            # must read as unreachable, never propagate to a 500. Broad by design, not an oversight.
            self.logger.debug(f"Sidecar '{name}' unreachable at {base_url}: {type(exc).__name__}")
            return ProbeResult(reachable=False, device=None, detail="unreachable")

        # 2. Only a 200 means ready-to-serve; a readiness 503 (model still loading) is reachable-but-not-ready.
        if response.status_code != 200:
            return ProbeResult(
                reachable=False, device=None, detail=f"not ready (HTTP {response.status_code})"
            )

        # 3. Surface the device the sidecar advertises on /health (bge/paddle/mineru/dots emit
        #    "cuda"/"cpu"); None when a sidecar omits the field.
        device = self.__read_device(response)
        return ProbeResult(reachable=True, device=device, detail=None)

    def __read_device(self, response: httpx.Response) -> str | None:
        """Extract a string ``device`` field from a /health JSON body, or None when absent/non-JSON."""
        # 1. A non-JSON or fieldless body is normal (the current sidecars expose no device) — no error.
        try:
            body = response.json()
        except ValueError:
            return None
        device = body.get("device") if isinstance(body, dict) else None
        return device if isinstance(device, str) else None

    async def __refresh(self, targets: dict[str, str]) -> dict[str, ProbeResult]:
        """Probe every target concurrently under one short-lived client and return the fresh map."""
        # 1. One client for the whole round; probes run concurrently, each self-contained (never raises).
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            names = list(targets)
            results = await asyncio.gather(
                *(self.__probe_one(client, name, targets[name]) for name in names)
            )
        return dict(zip(names, results, strict=True))

    async def probe(self, targets: dict[str, str]) -> dict[str, ProbeResult]:
        """
        Return the reachability map for the given sidecars, reusing a fresh-enough cached round.

        Args:
            targets (dict[str, str]): Sidecar name → base URL to probe.

        Returns:
            dict[str, ProbeResult]: One result per target name.
        """
        # 1. Serve the cache while it is within its TTL — a burst of calls costs a single probe round.
        now = time.monotonic()
        if self._cache is not None and (now - self._cached_at) < self._cache_ttl_seconds:
            return self._cache

        # 2. Refresh under the lock so concurrent callers coalesce onto one round (re-check inside).
        async with self._lock:
            now = time.monotonic()
            if self._cache is not None and (now - self._cached_at) < self._cache_ttl_seconds:
                return self._cache
            self._cache = await self.__refresh(targets)
            self._cached_at = time.monotonic()
            return self._cache


__all__ = ["ProbeResult", "SidecarProbe"]
