# ====== Code Summary ======
# Static helpers for making an arbitrary user-controlled string safe to interpolate into a log line.
# Any value a client controls (an uploaded filename, a collection or key name) can carry CR/LF, tabs
# or other control bytes that let it forge extra log records (log/line splitting) or bloat a line with
# unbounded junk. This mirrors RequestIdHelpers._sanitise (which constrains inbound correlation ids for
# exactly this reason) but for FREE-TEXT names: it strips control characters, collapses whitespace
# runs, caps the length, and returns a visible placeholder when nothing printable remains.

from __future__ import annotations

# ====== Standard Library Imports ======
import re

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# Every C0/C1 control character (includes CR, LF and tab) — the bytes that enable log-line splitting.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
# A run of any remaining whitespace, collapsed to a single space so a line stays on one row.
_WHITESPACE_RUN = re.compile(r"\s+")
# Hard cap so a hostile or accidental giant name cannot bloat a log line.
_MAX_LENGTH = 256
# What a value that held nothing printable renders as (never an empty gap in the log line).
_EMPTY_PLACEHOLDER = "<empty>"


class LogSafeHelpers:
    """Static-only helpers for sanitising user-controlled strings before they reach a log line."""

    logger = loggerplusplus.bind(identifier="LogSafeHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("LogSafeHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def sanitize(cls, value: str, max_length: int = _MAX_LENGTH) -> str:
        """
        Return a log-safe rendering of an arbitrary user-controlled string.

        Strips control characters (CR/LF/tab and the rest of the C0/C1 range) that would let the
        value forge extra log records, collapses remaining whitespace runs to a single space, caps
        the length, and substitutes a placeholder when nothing printable survives.

        Args:
            value (str): The raw user-controlled value (e.g. an uploaded filename or a name field).
            max_length (int): The maximum number of characters to keep (defaults to 256).

        Returns:
            str: The sanitised value, or ``<empty>`` when it held no printable characters.
        """
        # 1. Drop every control character (kills CR/LF/tab used for log-line splitting).
        without_controls = _CONTROL_CHARS.sub(" ", value)

        # 2. Collapse any resulting whitespace runs and trim the edges to a single clean line.
        collapsed = _WHITESPACE_RUN.sub(" ", without_controls).strip()

        # 3. An empty result (all control/whitespace) renders as a visible placeholder, never a gap.
        if not collapsed:
            return _EMPTY_PLACEHOLDER

        # 4. Bound the length so a giant value cannot bloat the log line.
        return collapsed[:max_length]


__all__ = ["LogSafeHelpers"]
