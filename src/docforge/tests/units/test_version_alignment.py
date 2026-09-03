"""Lockstep-version guard: docforge, mcp and the SDK must ALWAYS carry the same version.

The repo ships every artifact under one unified version (a single ``v*`` tag builds all images AND
publishes the SDK at that number). This test fails the gate the moment the three version sources drift
— so a release can never ship, say, docforge 0.13.0 with an SDK still at 0.9.12 again.
"""

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[3]  # …/src


def _toml_version(path: pathlib.Path) -> str:
    """Read the first ``version = "x.y.z"`` from a pyproject.toml."""
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', path.read_text())
    assert match, f"no version in {path}"
    return match.group(1)


def _sdk_version(path: pathlib.Path) -> str:
    """Read ``__version__ = "x.y.z"`` from the SDK's _version.py."""
    match = re.search(r'__version__\s*=\s*"([^"]+)"', path.read_text())
    assert match, f"no __version__ in {path}"
    return match.group(1)


def test_docforge_mcp_sdk_versions_are_aligned() -> None:
    """The three version sources are identical (unified lockstep release)."""
    docforge = _toml_version(_ROOT / "docforge" / "pyproject.toml")
    mcp = _toml_version(_ROOT / "mcp" / "pyproject.toml")
    sdk = _sdk_version(_ROOT / "docforge_sdk" / "docforge_sdk" / "_version.py")
    assert docforge == mcp == sdk, (
        f"version drift — docforge={docforge}, mcp={mcp}, sdk={sdk}. "
        "Bump all three together with scripts/set_version.sh before tagging."
    )
