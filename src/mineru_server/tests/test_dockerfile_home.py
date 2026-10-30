"""Regression test for issue #227: the runtime image's user must own an existing home directory.

Docker sets HOME from the passwd entry (/home/appuser); modelscope (~/.cache/modelscope) and
huggingface_hub (~/.cache/huggingface) create their dirs under it, so a missing home made the
model download fail with Permission denied. Serviceless: parses the Dockerfile statically.
"""

import pathlib
import re

_DOCKERFILE = pathlib.Path(__file__).resolve().parent.parent / "Dockerfile"


def _runtime_stage() -> str:
    """Return the text of the runtime stage, line continuations joined."""
    text = _DOCKERFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    return text.split(" AS runtime", 1)[1]


def _useradd_line() -> str:
    """Return the runtime stage's `useradd ... appuser` command."""
    match = re.search(r"useradd\s[^\n]*\bappuser\s*$", _runtime_stage(), re.MULTILINE)
    assert match, "the runtime stage creates no `appuser` with useradd"
    return match[0]


def test_runtime_user_gets_a_home_directory() -> None:
    """The runtime user is created with its home directory."""
    line = _useradd_line()
    assert "--no-create-home" not in line and "-M " not in line
    assert "--create-home" in line or re.search(r"(^|\s)-m(\s|$)", line)


def test_runtime_user_home_is_home_appuser() -> None:
    """The home directory, when given explicitly, is /home/appuser."""
    line = _useradd_line()
    home = re.search(r"--home-dir\s+(\S+)", line)
    assert home is None or home[1] == "/home/appuser"


def test_user_is_created_before_dropping_root() -> None:
    """useradd runs as root, before the stage switches to the runtime user."""
    stage = _runtime_stage()
    assert stage.index("useradd") < stage.index("USER appuser")
