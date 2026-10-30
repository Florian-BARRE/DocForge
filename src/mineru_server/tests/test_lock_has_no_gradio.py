"""Guards the locked dependency set: no gradio (mineru's web demo UI) and a starlette 1.x (pure, offline)."""

import pathlib
import tomllib

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _locked_versions() -> dict[str, str]:
    """Map each package of uv.lock to its locked version."""
    lock = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {package["name"]: package["version"] for package in lock["package"]}


def test_extras_do_not_request_mineru_core() -> None:
    """`mineru[core]` pulls `mineru[gradio]` (gradio==5.49.1); the extras list the parts the server needs."""
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for extra, requirements in pyproject["project"]["optional-dependencies"].items():
        mineru = [r for r in requirements if r.startswith("mineru[")]
        assert mineru, f"extra {extra} has no mineru requirement"
        assert all("core" not in r and "gradio" not in r for r in mineru), (extra, mineru)


def test_docs_do_not_name_mineru_core_as_the_extra() -> None:
    """The comments describing the install name the extras the server locks, not `mineru[core]`."""
    files = [
        _ROOT / "Dockerfile",
        _ROOT / "config_loader.py",
        _ROOT / "pyproject.toml",
        _ROOT.parent.parent / "services" / "mineru_server" / ".env.example",
    ]
    stale = [path.name for path in files if "mineru[core]" in path.read_text(encoding="utf-8")]
    assert not stale, stale


def test_lock_has_no_gradio() -> None:
    """The HTTP server never imports gradio: neither it nor gradio-pdf is locked."""
    versions = _locked_versions()
    assert not {"gradio", "gradio-client", "gradio-pdf"} & versions.keys()


def test_lock_starlette_is_past_the_advisories() -> None:
    """starlette 0.x (pinned under gradio 5) carries advisories fixed up to 1.3.1."""
    major, minor, patch = (int(part) for part in _locked_versions()["starlette"].split(".")[:3])
    assert (major, minor, patch) >= (1, 3, 1)
