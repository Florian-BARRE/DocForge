# ====== Code Summary ======
# Log-safe rendering of a RUNTIME_CONFIG for the startup dump, plus a reusable free-text redactor.
# configplusplus masks values whose ATTRIBUTE NAME contains a secret keyword
# (SECRET/API_KEY/PASSWORD/TOKEN/CREDENTIAL), but connection strings named POSTGRES_DSN / REDIS_URL
# carry their password in the VALUE (``scheme://user:pass@host``) under a name the heuristic never
# catches — so they would print in clear (and reach Loki). This helper renders the config through the
# library (keeping its name-based masking) and then redacts the userinfo of any URL/DSN in the output,
# regardless of the variable's name. The same userinfo redaction is exposed as ``redact_text`` so an
# arbitrary free-text string (a persisted provider exception message, a probe detail) can be scrubbed
# of embedded ``scheme://user:pass@host`` credentials before it is stored or returned to a client.

# ====== Standard Library Imports ======
import re
from typing import Any

# The authority userinfo of a URL/DSN: everything between ``://`` and the ``@`` that closes it. The
# character class stops at the first ``@`` or ``/``, so only the credentials segment is redacted — the
# scheme, host, port, path and query are preserved for diagnostics.
_URL_USERINFO = re.compile(r"(://)[^/@\s]+@")


class ConfigDumpHelpers:
    """Static helpers producing a log-safe string of a config object for the startup dump."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigDumpHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def redact_text(cls, text: str) -> str:
        """
        Redact any ``scheme://user:pass@host`` userinfo embedded anywhere in a free-text string.

        Used to scrub a persisted provider exception message (``job.error``) or a reachability probe
        detail: a provider whose ``base_url`` carries credentials (``https://user:pass@host``) can
        echo them back inside an error/timeout message. Only the userinfo segment is dropped — the
        scheme, host, port, path and the surrounding message are preserved so the diagnostic value is
        never lost.

        Args:
            text (str): The free-text string to scrub (e.g. an exception message).

        Returns:
            str: The same string with every URL/DSN userinfo replaced by ``scheme://***@``.
        """
        # 1. Replace only the credentials segment of each URL/DSN occurrence, in place.
        return _URL_USERINFO.sub(r"\1***@", text)

    @classmethod
    def masked(cls, config: Any) -> str:
        """
        Render a config object for logging with URL/DSN credentials redacted.

        The object is first stringified through configplusplus (which masks values whose attribute
        name looks like a secret), then any ``scheme://user:pass@host`` userinfo remaining in the
        output is replaced with ``scheme://***@host`` — catching POSTGRES_DSN / REDIS_URL and any
        other credential-bearing URL the name heuristic misses.

        Args:
            config (Any): The config object (e.g. RUNTIME_CONFIG) to render.

        Returns:
            str: The rendered config with all URL/DSN credentials redacted.
        """
        # 1. Stringify through the library (name-based masking), then scrub value-embedded userinfo.
        return cls.redact_text(str(config))


__all__ = ["ConfigDumpHelpers"]
