# ====== Code Summary ======
# ProbeStatus — the closed outcome vocabulary of one provider reachability probe. It is the honest
# projection of a node's preflight() result onto a small, UI-friendly enum: the endpoint answered
# (ok), never answered (unreachable), rejected the credentials (auth_failed), was refused by the
# egress allowlist BEFORE any network probe (blocked), or there was nothing to probe (not_configured
# for an expected-but-absent provider, skipped for a leaf with no endpoint).

# ====== Standard Library Imports ======
from enum import StrEnum


class ProbeStatus(StrEnum):
    """
    The outcome of probing one provider-hosted node for reachability.

    Attributes:
        OK: The endpoint answered (any non-auth status) — reachable with accepted credentials.
        UNREACHABLE: The endpoint never answered (DNS/refused/timeout) or the probe timed out.
        AUTH_FAILED: The endpoint answered but rejected the credentials (HTTP 401/403).
        BLOCKED: The endpoint's host is not on the egress allowlist — refused WITHOUT probing (so
            the health sweep cannot be turned into a network scanner and the worker never spends).
        NOT_CONFIGURED: A provider that was expected in the graph is absent (nothing to probe).
        SKIPPED: A local action leaf with no endpoint to probe (no preflight override).
    """

    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    BLOCKED = "blocked"
    NOT_CONFIGURED = "not_configured"
    SKIPPED = "skipped"


__all__ = ["ProbeStatus"]
