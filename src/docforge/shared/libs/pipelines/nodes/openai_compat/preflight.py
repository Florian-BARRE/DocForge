# ====== Code Summary ======
# EndpointReachability — the ONE cheap HTTP probe every provider node reuses in its preflight():
# is the configured endpoint reachable, and are the credentials accepted? It closes the honest gap
# in "fail-fast before spend" — GraphValidator is structural only, so a wrong/unreachable base_url
# builds cleanly and would otherwise fail mid-run, after earlier stages already spent. This probe
# runs after build, before the first spend, and NEVER makes a real model call: a GET to the base's
# /models (or any lightweight route) is enough. Semantics are deliberately narrow to avoid false
# positives: a connection failure (DNS/refused/timeout) is fatal, a 401/403 is fatal, and ANY other
# HTTP status means the host answered — reachable — so it passes.

# ====== Standard Library Imports ======
import base64

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


class EndpointIncompatibleError(PreflightError):
    """The endpoint answered but a REQUIRED route is absent (HTTP 404) — wrong server kind.

    Distinct from unreachable (host down) and auth (creds rejected): the host is up and creds pass,
    but it does not expose the specific route the node calls (e.g. a TEI-only server that has no
    ``/v1/embeddings``). Surfaced by the capability probe, never by the plain reachability check.
    """


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
        basic_auth: tuple[str, str] | None = None,
        timeout_seconds: float = _DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
        path: str = "/models",
    ) -> None:
        """
        Probe an endpoint's reachability and credentials without spending a real call.

        Args:
            node_kind (str): The calling node's KIND, named in the error for a clear message.
            base_url (str): The endpoint base URL to reach (per-collection config).
            api_key (str): Bearer token sent when non-empty (lets the probe surface a 401/403).
            basic_auth (tuple[str, str] | None): ``(username, password)`` for an endpoint behind
                HTTP basic auth (e.g. a remote Gotenberg). When set it authenticates the probe with a
                Basic ``Authorization`` header INSTEAD of the bearer, so an authed ``/health`` reads
                as reachable rather than a 401. Mutually exclusive with ``api_key`` — basic_auth wins.
            timeout_seconds (float): Per-attempt probe timeout — the node's configured
                ``preflight_timeout_seconds``, used as-is (no ceiling; the config wins).
            path (str): The lightweight route appended to ``base_url`` (defaults to ``/models``).

        Raises:
            PreflightError: The host is unreachable (DNS/refused/timeout, after the retries) or the
                credentials are rejected (HTTP 401/403). Any other status is treated as reachable.
        """
        # A plain reachability check: any answered status (bar 401/403) proves the host is up.
        await cls.__probe(
            node_kind=node_kind,
            base_url=base_url,
            api_key=api_key,
            basic_auth=basic_auth,
            timeout_seconds=timeout_seconds,
            path=path,
        )

    @classmethod
    async def check_route_present(
        cls,
        *,
        node_kind: str,
        base_url: str,
        path: str,
        capability_hint: str,
        api_key: str = "",
        timeout_seconds: float = _DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    ) -> None:
        """
        Probe that a SPECIFIC route exists, not merely that the host answers.

        Unlike :meth:`check` — which treats any non-auth status as reachable — this treats a 404 as
        fatal: the host is up and the credentials pass, but the exact route the node will POST to is
        absent (the classic case: a TEI-only server that has no ``/v1/embeddings``). A GET to a
        POST-only route that DOES exist answers 405/422/200 (route present), so only a 404 is read as
        "route missing". The distinction turns an opaque mid-run 404 into an actionable preflight error.

        Args:
            node_kind (str): The calling node's KIND, named in the error for a clear message.
            base_url (str): The endpoint base URL (per-collection config).
            path (str): The route appended to ``base_url`` that the node actually calls (its presence
                is the capability being verified, e.g. ``/embeddings`` on an OpenAI-compatible base).
            capability_hint (str): Actionable guidance appended to the 404 error (what the endpoint
                must expose and how to fix a mispointed ``base_url``).
            api_key (str): Bearer token sent when non-empty (lets the probe surface a 401/403).
            timeout_seconds (float): Per-attempt probe timeout — the node's ``preflight_timeout_seconds``.

        Raises:
            EndpointUnreachableError: The host did not answer (DNS/refused/timeout, after retries).
            EndpointAuthError: The credentials were rejected (HTTP 401/403).
            EndpointIncompatibleError: The host answered 404 — the required route is absent.
        """
        status_code = await cls.__probe(
            node_kind=node_kind,
            base_url=base_url,
            api_key=api_key,
            basic_auth=None,
            timeout_seconds=timeout_seconds,
            path=path,
        )
        if status_code == 404:
            raise EndpointIncompatibleError(
                f"{node_kind}: {base_url.rstrip('/')}{path} not found (HTTP 404) — {capability_hint}"
            )

    @classmethod
    async def __probe(
        cls,
        *,
        node_kind: str,
        base_url: str,
        api_key: str,
        basic_auth: tuple[str, str] | None,
        timeout_seconds: float,
        path: str,
    ) -> int:
        """Run the retry loop and return the answered HTTP status (transport/auth failures raise).

        The shared core of :meth:`check` and :meth:`check_route_present`: transport errors are fatal
        after the retries, a 401/403 is fatal, and any other status is RETURNED for the caller to
        interpret (reachability accepts anything; the capability probe rejects a 404).
        """
        # 1. Build the probe URL + credentials. Basic auth wins over the bearer when both are given (a
        #    remote behind basic auth). The configured timeout is used directly — the sweep bounds the
        #    overall probe, so preflight no longer needs to cap the per-attempt value.
        url = base_url.rstrip("/") + path
        if basic_auth is not None:
            token = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode()).decode("ascii")
            headers = {"Authorization": f"Basic {token}"}
        elif api_key:
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
            headers = {}
        timeout = timeout_seconds

        # 2. Try once, retry on a transport error to absorb a transient blip.
        last_error: Exception | None = None
        for _attempt in range(RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url, headers=headers)
            except httpx.TransportError as exc:
                # DNS failure, connection refused, connect/read timeout — the host did not answer.
                last_error = exc
                continue
            # 3. The host answered: rejected credentials are fatal, any other status is returned.
            if response.status_code in (401, 403):
                raise EndpointAuthError(
                    f"{node_kind}: credentials rejected by {base_url} "
                    f"(HTTP {response.status_code}) — check the api_key"
                )
            cls.logger.debug(
                f"{node_kind}: endpoint {base_url} reachable (HTTP {response.status_code})"
            )
            return response.status_code

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
    "EndpointIncompatibleError",
]
