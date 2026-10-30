# ====== Code Summary ======
# Regression test for issue #224: the runtime image's user must own an existing home directory.
# Docker sets HOME from the passwd entry (/home/appuser); huggingface_hub (~/.cache/huggingface) and
# modelscope (~/.cache/modelscope) create their dirs under it, so a missing home made every model
# download fail with Permission denied and paddlex fall back to the bcebos mirror.
# Serviceless: parses the Dockerfile statically.

# ====== Standard Library Imports ======
import pathlib
import re

# tests/unit/<this> → parents[2] is src/paddle_server.
_DOCKERFILE = pathlib.Path(__file__).resolve().parents[2] / "Dockerfile"


def _runtime_stage() -> str:
    text = _DOCKERFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    return text.split(" AS runtime", 1)[1]


def _useradd_line() -> str:
    match = re.search(r"useradd\s[^\n]*\bappuser\s*$", _runtime_stage(), re.MULTILINE)
    assert match, "the runtime stage creates no `appuser` with useradd"
    return match[0]


def test_runtime_user_gets_a_home_directory() -> None:
    line = _useradd_line()
    assert "--no-create-home" not in line and "-M " not in line
    assert "--create-home" in line or re.search(r"(^|\s)-m(\s|$)", line)


def test_runtime_user_home_is_home_appuser() -> None:
    line = _useradd_line()
    home = re.search(r"--home-dir\s+(\S+)", line)
    assert home is None or home[1] == "/home/appuser"
