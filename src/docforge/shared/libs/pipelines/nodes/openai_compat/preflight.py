# ====== Code Summary ======
# EndpointReachability — the ONE cheap HTTP probe every provider node reuses in its preflight():
# is the configured endpoint reachable, and are the credentials accepted? It closes the honest gap
# in "fail-fast before spend" — GraphValidator is structural only, so a wrong/unreachable base_url
# builds cleanly and would otherwise fail mid-run, after earlier stages already spent. This probe
# runs after build, before the first spend, and NEVER makes a real model call: a GET to the base's
# /models (or any lightweight route) is enough. Semantics are deliberately narrow to avoid false
# positives: a connection failure (DNS/refused/timeout) is fatal, a 401/403 is fatal, and ANY other
# HTTP status means the host answered — reachable — so it passes.

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import loggerplusplus

# Default per-attempt probe timeout when a caller passes none. Nodes now forward their configured
# ``preflight_timeout_seconds`` (a dedicated, per-collection knob), so the probe is NO LONGER capped
# here — the config wins. This value is only the fallback for a caller that omits it. It is 10s (not a
# couple of seconds) because a real hosted endpoint's FIRST probe pays a cold TLS handshake + routing
# that legitimately exceeds a few seconds; a 5s ceiling turned that latency into spurious failures.
_DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 10.0

# Retries after the initial attempt. Two absorb a transient blip; a genuinely unreachable endpoint
# still fails loudly after them. Exposed as a named default so the sweep can size its outer bound.
RETRIES = 2


class PreflightError(Exception):
    """A provider's preflight reachability/credential check failed before any spend."""


class EndpointUnreachableError(PreflightError):
    """The endpoint did not answer (DNS/refused/timeout) — a transport-level failure."""


class EndpointAuthError(PreflightError):
    """The endpoint answered but rejected the credentials (HTTP 401/403)."""


class EndpointReachability:
    """Static HTTP reachability probe shared by every provider node's ``preflight()``."""

    logger = loggerplusplus.bind(identifier="EndpointReachability")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EndpointReachability is a static-only class and cannot be instantiated.")

    @staticmethod
    def budget(timeout_seconds: float = _DEFAULT_PREFLIGHT_TIMEOUT_SECONDS) -> float:
        """Worst-case wall-clock of one full probe: every attempt paying its whole timeout.

        The sweep sizes its outer per-node cap from this so the probe's OWN retries always complete
        before the sweep would kill them (the pre-fix bug: a 5 s outer cap fired before the 10 s probe).
        """
        return timeout_seconds * (RETRIES + 1)

    @classmethod
    async def check(
        cls,
        *,
        node_kind: str,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = _DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
        path: str = "/models",
    ) -> None:
        """
        Probe an endpoint's reachability and credentials without spending a real call.

        Args:
            node_kind (str): The calling node's KIND, named in the error for a clear message.
            base_url (str): The endpoint base URL to reach (per-collection config).
            api_key (str): Bearer token sent when non-empty (lets the probe surface a 401/403).
            timeout_seconds (float): Per-attempt probe timeout — the node's configured
                ``preflight_timeout_seconds``, used as-is (no ceiling; the config wins).
            path (str): The lightweight route appended to ``base_url`` (defaults to ``/models``).

        Raises:
            PreflightError: The host is unreachable (DNS/refused/timeout, after the retries) or the
                credentials are rejected (HTTP 401/403). Any other status is treated as reachable.
        """
        # 1. Build the probe URL + optional bearer. The configured timeout is used directly — the
        #    sweep bounds the overall probe, so preflight no longer needs to cap the per-attempt value.
        url = base_url.rstrip("/") + path
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        timeout = timeout_seconds

        # 2. Try once, retry on a transport error to absorb a transient blip.
        last_error: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url, headers=headers)
            except httpx.TransportError as exc:
                # DNS failure, connection refused, connect/read timeout — the host did not answer.
                last_error = exc
                continue
            # 3. The host answered: rejected credentials are fatal, any other status is reachable.
            if response.status_code in (401, 403):
                raise EndpointAuthError(
                    f"{node_kind}: credentials rejected by {base_url} "
                    f"(HTTP {response.status_code}) — check the api_key"
                )
            cls.logger.debug(
                f"{node_kind}: endpoint {base_url} reachable (HTTP {response.status_code})"
            )
            return

        # 4. Every attempt failed to connect — a genuine unreachable endpoint, fail loudly.
        raise EndpointUnreachableError(
            f"{node_kind}: endpoint unreachable at {base_url} "
            f"({type(last_error).__name__}: {last_error})"
        )


__all__ = [
    "EndpointReachability",
    "PreflightError",
    "EndpointUnreachableError",
    "EndpointAuthError",
]
