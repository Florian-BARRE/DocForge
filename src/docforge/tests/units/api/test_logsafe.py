"""LogSafeHelpers: user-controlled strings are made safe to interpolate into a log line — control
characters (CR/LF/tab) that enable log-line splitting are stripped, whitespace runs collapse, the
length is capped, and an all-control/whitespace value renders as a visible placeholder.

``from backend...`` is deferred inside each test until the ``fastapi_app`` fixture has registered
app/ on sys.path (the same constraint test_auth.py documents).
"""


def test_strips_crlf_used_for_log_line_splitting(fastapi_app) -> None:
    """CR/LF (and the surrounding forged record) collapse to a single space — no extra log line."""
    from backend.libs.logsafe import LogSafeHelpers  # noqa: PLC0415

    out = LogSafeHelpers.sanitize("real.pdf\r\nINFO forged log record")
    assert "\r" not in out and "\n" not in out
    assert out == "real.pdf INFO forged log record"


def test_collapses_tabs_and_whitespace_runs(fastapi_app) -> None:
    """Tabs and repeated whitespace collapse so the value stays on one clean row."""
    from backend.libs.logsafe import LogSafeHelpers  # noqa: PLC0415

    assert LogSafeHelpers.sanitize("a\t\t b   c") == "a b c"


def test_all_control_or_whitespace_renders_placeholder(fastapi_app) -> None:
    """A value that held nothing printable becomes a visible placeholder, never an empty gap."""
    from backend.libs.logsafe import LogSafeHelpers  # noqa: PLC0415

    assert LogSafeHelpers.sanitize("\r\n\t   ") == "<empty>"


def test_length_is_capped(fastapi_app) -> None:
    """A giant value cannot bloat a log line — it is truncated to the cap."""
    from backend.libs.logsafe import LogSafeHelpers  # noqa: PLC0415

    out = LogSafeHelpers.sanitize("x" * 5000, max_length=256)
    assert len(out) == 256


def test_ordinary_name_is_returned_verbatim(fastapi_app) -> None:
    """A well-behaved name passes through unchanged (full diagnostic value)."""
    from backend.libs.logsafe import LogSafeHelpers  # noqa: PLC0415

    assert LogSafeHelpers.sanitize("Quarterly Report 2026.pdf") == "Quarterly Report 2026.pdf"
