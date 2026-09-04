# ====== Code Summary ======
# PathGuard confines the `file_path` argument of path-based tools (upload_document,
# import_collection) to an operator-configured inbox directory whenever the call arrived over an
# untrusted transport (streamable-HTTP). Without this guard, any caller holding nothing more than a
# valid DocForge API key could make the MCP container read ANY file its own OS user can see (e.g.
# /proc/1/environ) and exfiltrate it by uploading it into a collection they control. On stdio the
# caller already has local shell access to whatever it names, so confinement is skipped there.

from __future__ import annotations

# ====== Standard Library Imports ======
from pathlib import Path

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class PathGuardError(ValueError):
    """Raised when a `file_path` tool argument is refused by PathGuard."""


class PathGuard(LoggerClass):
    """
    Resolves and, when required, confines local file paths supplied to path-based tools.

    With ``confine=False`` (stdio) every path is returned unchanged — the caller is the local,
    single-trusted-user process this transport is designed for. With ``confine=True``
    (streamable-HTTP) a path is only accepted when an inbox directory is configured AND the
    resolved, symlink-followed real path stays inside it; anything else (no inbox configured,
    ``..`` traversal, an absolute path elsewhere, a symlink pointing outside) is refused before the
    SDK is ever called, so the DocForge API never sees a read of a file outside the inbox.
    """

    def __init__(self, *, confine: bool, inbox_dir: Path | None) -> None:
        """
        Args:
            confine (bool): True on transports where the caller must not read arbitrary files
                (streamable-HTTP); False where local path reads are the intended behaviour (stdio).
            inbox_dir (Path | None): The one directory HTTP callers may stage files into/read from.
                None disables path-based tools entirely while confined.
        """
        LoggerClass.__init__(self)
        self._confine = confine
        self._inbox_dir = inbox_dir.resolve() if inbox_dir is not None else None

    def resolve(self, file_path: str) -> Path:
        """
        Resolve a tool-supplied path, enforcing inbox confinement when required.

        Args:
            file_path (str): The caller-supplied path — absolute, or relative to the inbox.

        Returns:
            Path: The path to hand to the SDK for reading.

        Raises:
            PathGuardError: Confinement applies and either no inbox is configured, or the resolved
                path (symlinks followed) escapes the configured inbox directory.
        """
        # 1. stdio — unchanged behaviour, no confinement.
        if not self._confine:
            return Path(file_path)

        # 2. No inbox configured on a confined transport — refuse outright rather than fall back
        #    to an unrestricted read of the container's filesystem.
        if self._inbox_dir is None:
            raise PathGuardError(
                "Path-based file tools are disabled on this deployment: no upload inbox is "
                "configured (operator must set MCP_UPLOAD_DIR and stage the file there)."
            )

        # 3. Join relative paths under the inbox, then resolve (follows symlinks, normalizes '..')
        #    BEFORE the containment check, so neither traversal nor a symlink pointing outside the
        #    inbox can escape it.
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = self._inbox_dir / candidate
        resolved = candidate.resolve()

        try:
            resolved.relative_to(self._inbox_dir)
        except ValueError:
            self.logger.warning(
                f"Refused file_path '{file_path}' resolving to '{resolved}', outside inbox "
                f"'{self._inbox_dir}'"
            )
            raise PathGuardError(
                f"Refused: '{file_path}' resolves outside the configured upload inbox."
            ) from None

        return resolved


__all__ = ["PathGuard", "PathGuardError"]
