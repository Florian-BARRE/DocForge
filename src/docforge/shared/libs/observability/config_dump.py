# ====== Code Summary ======
# Log-safe rendering of a RUNTIME_CONFIG for the startup dump. configplusplus masks values whose
# ATTRIBUTE NAME contains a secret keyword (SECRET/API_KEY/PASSWORD/TOKEN/CREDENTIAL), but connection
# strings named POSTGRES_DSN / REDIS_URL carry their password in the VALUE (``scheme://user:pass@host``)
# under a name the heuristic never catches — so they would print in clear (and reach Loki). This helper
# renders the config through the library (keeping its name-based masking) and then redacts the userinfo
# of any URL/DSN in the output, regardless of the variable's name.

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
        return _URL_USERINFO.sub(r"\1***@", str(config))


__all__ = ["ConfigDumpHelpers"]
