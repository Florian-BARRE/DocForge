# ====== Code Summary ======
# ProbeStatus — the closed outcome vocabulary of one provider reachability probe. It is the honest
# projection of a node's preflight() result onto a small, UI-friendly enum: the endpoint answered
# (ok), never answered (unreachable), rejected the credentials (auth_failed), or there was nothing
# to probe (not_configured for an expected-but-absent provider, skipped for a leaf with no endpoint).

# ====== Standard Library Imports ======
from enum import StrEnum


class ProbeStatus(StrEnum):
    """
    The outcome of probing one provider-hosted node for reachability.

    Attributes:
        OK: The endpoint answered (any non-auth status) — reachable with accepted credentials.
        UNREACHABLE: The endpoint never answered (DNS/refused/timeout) or the probe timed out.
        AUTH_FAILED: The endpoint answered but rejected the credentials (HTTP 401/403).
        NOT_CONFIGURED: A provider that was expected in the graph is absent (nothing to probe).
        SKIPPED: A local action leaf with no endpoint to probe (no preflight override).
    """

    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    NOT_CONFIGURED = "not_configured"
    SKIPPED = "skipped"


__all__ = ["ProbeStatus"]
