# ====== Code Summary ======
# Unit tests for libs/path_guard.py: PathGuard is the transport-aware confinement guard behind the
# 0.14.0 audit finding (upload_document / import_collection could read ANY file the MCP container's
# OS user could see). Unconfined (stdio) leaves paths untouched; confined (streamable-HTTP) requires
# an inbox directory and refuses traversal, an absolute path elsewhere, and a symlink escape.

from __future__ import annotations

# ====== Standard Library Imports ======
from pathlib import Path

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.path_guard import PathGuard, PathGuardError


def test_unconfined_transport_returns_arbitrary_path_unchanged(tmp_path: Path) -> None:
    """stdio (confine=False): any local path is returned as-is, no inbox required."""
    guard = PathGuard(confine=False, inbox_dir=None)
    outside = tmp_path / "elsewhere" / "secret.env"

    resolved = guard.resolve(str(outside))

    assert resolved == Path(str(outside))


def test_confined_transport_with_no_inbox_refuses_everything(tmp_path: Path) -> None:
    """HTTP (confine=True) with no MCP_UPLOAD_DIR configured: every path is refused."""
    guard = PathGuard(confine=True, inbox_dir=None)

    with pytest.raises(PathGuardError):
        guard.resolve(str(tmp_path / "anything.pdf"))


def test_confined_transport_allows_path_inside_inbox(tmp_path: Path) -> None:
    """HTTP + a path that resolves inside the configured inbox: allowed."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    staged = inbox / "report.pdf"
    staged.write_bytes(b"%PDF-1.4")
    guard = PathGuard(confine=True, inbox_dir=inbox)

    resolved = guard.resolve(str(staged))

    assert resolved == staged.resolve()


def test_confined_transport_allows_relative_path_under_inbox(tmp_path: Path) -> None:
    """A bare filename (no leading slash) is joined under the inbox, not the process cwd."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "report.pdf").write_bytes(b"%PDF-1.4")
    guard = PathGuard(confine=True, inbox_dir=inbox)

    resolved = guard.resolve("report.pdf")

    assert resolved == (inbox / "report.pdf").resolve()


def test_confined_transport_refuses_traversal_out_of_inbox(tmp_path: Path) -> None:
    """`../` traversal that resolves outside the inbox is refused."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (tmp_path / "secret.env").write_text("DOCFORGE_API_TOKEN=root")
    guard = PathGuard(confine=True, inbox_dir=inbox)

    with pytest.raises(PathGuardError):
        guard.resolve("../secret.env")


def test_confined_transport_refuses_absolute_path_outside_inbox(tmp_path: Path) -> None:
    """An absolute path pointing outside the inbox is refused even though it doesn't use `..`."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    outside = tmp_path / "proc_environ_lookalike"
    outside.write_text("SECRET=1")
    guard = PathGuard(confine=True, inbox_dir=inbox)

    with pytest.raises(PathGuardError):
        guard.resolve(str(outside))


def test_confined_transport_allows_absolute_path_already_inside_inbox(tmp_path: Path) -> None:
    """An absolute path that already lives inside the inbox is accepted (not just relative names)."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    staged = inbox / "nested" / "doc.pdf"
    staged.parent.mkdir()
    staged.write_bytes(b"%PDF-1.4")
    guard = PathGuard(confine=True, inbox_dir=inbox)

    resolved = guard.resolve(str(staged.absolute()))

    assert resolved == staged.resolve()


def test_confined_transport_refuses_symlink_escaping_inbox(tmp_path: Path) -> None:
    """A symlink staged inside the inbox but pointing outside it is refused (real path escapes)."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("DOCFORGE_API_TOKEN=root")
    escape_link = inbox / "looks-safe.pdf"
    escape_link.symlink_to(secret)
    guard = PathGuard(confine=True, inbox_dir=inbox)

    with pytest.raises(PathGuardError):
        guard.resolve(str(escape_link))
