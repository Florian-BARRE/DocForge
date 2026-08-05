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

# Hard cap on the probe timeout: preflight must be quick even when a node's config allows a long
# per-request timeout for real generation. A single retry absorbs a transient blip; a real refusal
# still fails loudly after it.
_MAX_TIMEOUT_SECONDS = 5.0
_RETRIES = 1


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

    @classmethod
    async def check(
        cls,
        *,
        node_kind: str,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = _MAX_TIMEOUT_SECONDS,
        path: str = "/models",
    ) -> None:
        """
        Probe an endpoint's reachability and credentials without spending a real call.

        Args:
            node_kind (str): The calling node's KIND, named in the error for a clear message.
            base_url (str): The endpoint base URL to reach (per-collection config).
            api_key (str): Bearer token sent when non-empty (lets the probe surface a 401/403).
            timeout_seconds (float): Requested timeout, hard-capped at ``_MAX_TIMEOUT_SECONDS``.
            path (str): The lightweight route appended to ``base_url`` (defaults to ``/models``).

        Raises:
            PreflightError: The host is unreachable (DNS/refused/timeout, after one retry) or the
                credentials are rejected (HTTP 401/403). Any other status is treated as reachable.
        """
        # 1. Build the probe URL + optional bearer; cap the timeout so preflight stays quick.
        url = base_url.rstrip("/") + path
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        timeout = min(timeout_seconds, _MAX_TIMEOUT_SECONDS)

        # 2. Try once, retry once on a transport error to absorb a transient blip.
        last_error: Exception | None = None
        for attempt in range(_RETRIES + 1):
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
