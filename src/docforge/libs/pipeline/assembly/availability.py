# ====== Code Summary ======
# Network availability probes for ProviderRegistry.
# ProviderUnavailableError is defined here because it is raised exclusively when an
# availability check fails — co-locating the error with the probes keeps the semantics clear.
# AvailabilityProbes is a static-only helpers class: it has no instance state and groups the
# TCP/URL reachability utilities used by ProviderRegistry._build_splitter() and indirectly
# by the chain builders.

# ====== Standard Library Imports ======
import socket
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class ProviderUnavailableError(Exception):
    """
    Raised when a PipelineConfig requests a provider that cannot run in this deployment.

    Mapped to HTTP 422 by the router with an actionable message.

    Attributes:
        capability (str): Capability that failed to resolve (e.g. "ocr", "parse").
        provider (str): Requested provider/backend id.
        reason (str): Why it is unavailable.
    """

    def __init__(self, capability: str, provider: str, reason: str) -> None:
        self.capability = capability
        self.provider = provider
        self.reason = reason
        super().__init__(f"{capability}:{provider} unavailable — {reason}")


class AvailabilityProbes:
    """
    Static-only helpers for cheap network reachability checks.

    Used by ProviderRegistry before instantiating providers that depend on a local
    TCP service (e.g. semantic chunking with a TEI endpoint).  Cloud HTTPS endpoints
    are NOT probed here — they are assumed reachable and will surface an actionable
    error at the first API call if they are not.
    """

    logger = loggerplusplus.bind(identifier="AvailabilityProbes")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AvailabilityProbes is a static-only class and cannot be instantiated.")

    @staticmethod
    def tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
        """
        Attempt a short TCP connect and return True if the socket opens within the timeout.

        Args:
            host (str): Target hostname or IP address.
            port (int): Target TCP port.
            timeout (float): Connect timeout in seconds (default 1.0).

        Returns:
            bool: True when the connection succeeds; False on any error.
        """
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except Exception:
            return False

    @classmethod
    def endpoint_reachable(cls, base_url: str) -> bool:
        """
        Parse host/port from a URL and TCP-probe it.

        Args:
            base_url (str): HTTP/HTTPS base URL to probe.

        Returns:
            bool: True when the TCP connection succeeds within the probe timeout.
        """
        # 1. Guard against empty or unconfigured URLs before parsing
        if not base_url:
            return False
        parsed = urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False
        # 2. Fall back to the scheme's default port when none is explicit
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return cls.tcp_reachable(host, port)
