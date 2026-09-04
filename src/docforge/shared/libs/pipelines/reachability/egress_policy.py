# ====== Code Summary ======
# ProviderEgressPolicy — the pure, allowlist-based egress guard for provider base URLs. Every
# per-collection provider endpoint (base_url) is operator/tenant-writable, so an unrestricted
# reachability probe (or a runtime call) doubles as an authenticated port/host scanner of the
# internal Docker network. This policy answers ONE question — "is this destination allowed?" — from
# an operator-supplied allowlist of host globs AND IP/CIDR entries. It is DELIBERATELY allow-all when
# the allowlist is EMPTY (the shipped default, guard OFF, behaviour unchanged), so the in-stack
# hostname providers (bge_server, gotenberg, paddle_server) keep working out of the box. When the
# operator SETS the allowlist the guard is ON: only destinations that match an entry pass, everything
# else — including a malformed/host-less URL that cannot be validated — is refused. It reads NO config
# itself (purity); the value is supplied by the config-reading EDGE (health sweep / worker preflight).

# ====== Standard Library Imports ======
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from fnmatch import fnmatch
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class ProviderEgressPolicy:
    """
    Immutable allowlist policy deciding whether a provider base URL may be reached.

    Attributes:
        allow (tuple[str, ...]): The allowlist entries. Each is either a hostname glob
            (case-insensitive, ``fnmatch`` semantics — e.g. ``bge_server``, ``*.internal``) or an
            IP / CIDR (e.g. ``10.0.0.0/8``, ``127.0.0.1``). An EMPTY tuple means allow-all (OFF).
    """

    allow: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_spec(cls, spec: str | None) -> ProviderEgressPolicy:
        """
        Build a policy from a comma-separated allowlist string (the config-knob shape).

        Args:
            spec (str | None): Comma-separated host globs / CIDRs (empty / None → allow-all).

        Returns:
            ProviderEgressPolicy: The parsed policy (blank/whitespace-only entries dropped).
        """
        if not spec:
            return cls(allow=())
        entries = tuple(part.strip() for part in spec.split(",") if part.strip())
        return cls(allow=entries)

    @property
    def enabled(self) -> bool:
        """Whether the guard is ON (a non-empty allowlist)."""
        return bool(self.allow)

    def is_allowed(self, url: str | None) -> bool:
        """
        Decide whether a destination URL is permitted under this policy.

        Semantics: with an EMPTY allowlist every URL is allowed (guard OFF). With a non-empty
        allowlist (guard ON) a URL passes only when its host matches at least one entry — as a
        hostname glob OR, when the host is an IP literal, as an IP inside a listed CIDR/IP. A URL
        whose host cannot be extracted (malformed / scheme-less / host-less) is REFUSED when the
        guard is on, since it cannot be validated against the allowlist.

        Args:
            url (str | None): The provider base URL to check (per-collection, untrusted).

        Returns:
            bool: True when the destination is allowed to be reached.
        """
        # 1. Guard OFF (empty allowlist) → allow everything, behaviour unchanged.
        if not self.allow:
            return True

        # 2. Extract the host; a URL we cannot parse into a host is not validatable → refuse.
        host = self.__host_of(url)
        if not host:
            return False

        # 3. Interpret the host as an IP literal once (None when it is a name, not an address).
        host_ip = self.__ip_of(host)

        # 4. Allowed iff any allowlist entry matches — as a CIDR/IP (when the host is an IP) or as a
        #    hostname glob (always tried, so an in-stack service hostname can be listed verbatim).
        return any(self.__entry_matches(entry, host, host_ip) for entry in self.allow)

    @staticmethod
    def __host_of(url: str | None) -> str | None:
        """Extract the lowercase host (no port) from a URL, or None when it has none."""
        if not url:
            return None
        try:
            host = urlsplit(url).hostname
        except ValueError:
            return None
        return host.lower() if host else None

    @staticmethod
    def __ip_of(host: str) -> ipaddress._BaseAddress | None:
        """Parse a host as an IP address literal, or None when it is a hostname."""
        try:
            return ipaddress.ip_address(host)
        except ValueError:
            return None

    @staticmethod
    def __entry_matches(
        entry: str, host: str, host_ip: ipaddress._BaseAddress | None
    ) -> bool:
        """Whether one allowlist entry admits the given host (as CIDR/IP or hostname glob)."""
        # 1. Try the entry as an IP network first: it only matches an IP-literal host inside it.
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            network = None
        if network is not None:
            return host_ip is not None and host_ip in network

        # 2. Otherwise it is a hostname glob — match case-insensitively (entry already a plain str).
        return fnmatch(host, entry.lower())


__all__ = ["ProviderEgressPolicy"]
