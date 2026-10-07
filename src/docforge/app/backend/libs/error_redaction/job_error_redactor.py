# ====== Code Summary ======
# JobErrorRedactor — the API-edge masking of a job's failure message for non-technical readers. The
# worker stores ``job.error`` verbatim ("<ExcType>: <message>", userinfo already stripped), and a
# provider transport error echoes the deployment topology in it: the sidecar URL, its host:port, the
# request path. That is read_technical surface; a read_text caller still needs to know THAT and WHY
# the job failed, so the message is kept and only the network locators are replaced by a placeholder.
# The structured fields (error_type, failed node/kind, stage) are untouched by design.

# ====== Standard Library Imports ======
import re
from typing import TypeVar

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
from ..auth import AuthPrincipal, AuthzGuard, Capability

_Model = TypeVar("_Model", bound=BaseModel)

# What a masked locator renders as.
PLACEHOLDER = "<redacted>"

# Ordered: whole URLs first, so their host:port/path never survive a later, narrower pattern.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # scheme://host[:port]/path?query
    (re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s'\"<>)\]]+"), PLACEHOLDER),
    # urllib3 style: HTTPConnectionPool(host='bge_server', port=8000) … with url: /embed
    (re.compile(r"\bhost=(['\"]?)[^'\",)\s]+\1"), f"host={PLACEHOLDER}"),
    (re.compile(r"\bport=\d+"), f"port={PLACEHOLDER}"),
    (re.compile(r"\burl: ?/[^\s'\"]*"), f"url: {PLACEHOLDER}"),
    # IPv4 with an optional :port and /path
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?(?:/[^\s'\"]*)?"), PLACEHOLDER),
    # bare hostname:port[/path] (a letter-led host so a "12:30" timestamp is left alone)
    (re.compile(r"\b[a-zA-Z][\w.-]*:\d{2,5}\b(?:/[^\s'\"]*)?"), PLACEHOLDER),
)


class JobErrorRedactor:
    """Static helper masking network locators in a job error for callers without read_technical."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("JobErrorRedactor is a static-only class and cannot be instantiated.")

    @staticmethod
    def mask(error: str) -> str:
        """
        Replace every URL, host/port pair and request path in a failure message by a placeholder.

        Args:
            error (str): The stored failure message.

        Returns:
            str: The same message with its network locators masked.
        """
        # 1. Apply the patterns in order (widest first).
        for pattern, replacement in _PATTERNS:
            error = pattern.sub(replacement, error)
        return error

    @classmethod
    def for_principal(cls, error: str | None, principal: AuthPrincipal) -> str | None:
        """
        Serve a job error as the caller may see it: verbatim to read_technical, masked otherwise.

        Args:
            error (str | None): The stored failure message (None when the job did not fail).
            principal (AuthPrincipal): The authenticated caller.

        Returns:
            str | None: The error, masked unless the caller holds read_technical.
        """
        # 1. Nothing to mask, or a technical reader who may see the topology.
        if error is None or AuthzGuard.holds(principal, Capability.READ_TECHNICAL):
            return error

        # 2. Everyone else keeps the message, minus the locators.
        return cls.mask(error)

    @classmethod
    def shape(cls, model: _Model, principal: AuthPrincipal) -> _Model:
        """
        Return a response model whose ``error`` field is served as the caller may see it.

        Args:
            model (BaseModel): A response model carrying an ``error: str | None`` field.
            principal (AuthPrincipal): The authenticated caller.

        Returns:
            BaseModel: The same model for a technical reader, else a copy with the error masked.
        """
        # 1. Only copy when the served error actually differs.
        error = getattr(model, "error", None)
        served = cls.for_principal(error, principal)
        return model if served == error else model.model_copy(update={"error": served})


__all__ = ["JobErrorRedactor", "PLACEHOLDER"]
