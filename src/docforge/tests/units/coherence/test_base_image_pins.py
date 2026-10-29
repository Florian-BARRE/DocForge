# ====== Code Summary ======
# Coherence ratchet — every third-party image is pinned by an exact version tag AND a digest.
# A floating tag (python:3.12-slim-bookworm, gotenberg:8, redis:8-bookworm, uv's unversioned
# python3.12 tag...) silently changes what a rebuild or a `compose pull` ships. The tag stays next
# to the digest (`name:tag@sha256:...`) so Dependabot's docker and docker-compose scanners still
# read the version and bump both together. Covers each Dockerfile's `FROM` and every `image:` of
# the compose files, except the first-party GHCR images (`${DOCFORGE_TAG}`) and the local `:dev`
# builds. Serviceless: parses the files statically.

# ====== Standard Library Imports ======
import pathlib
import re

# ====== Third-Party Library Imports ======
import pytest

# tests/units/coherence/<this> → parents[3] is src/docforge; its parents[1] is the repo root.
_SRC_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REPO_ROOT = _SRC_ROOT.parents[1]

_DOCKERFILES = sorted((_REPO_ROOT / "src").glob("**/Dockerfile"))
_COMPOSE_FILES = sorted((_REPO_ROOT / "compose").glob("**/compose.*.yml"))

_FROM = re.compile(r"^FROM\s+(?:--platform=\S+\s+)?(\S+)", re.MULTILINE)
_IMAGE = re.compile(r"^\s+image:\s*(\S+)\s*$", re.MULTILINE)
_PINNED = re.compile(r"^[a-z0-9./_-]+:(?P<tag>[A-Za-z0-9._-]+)@sha256:[0-9a-f]{64}$")
# The tag's leading version: v1.20.0, 3.12.16-slim-bookworm, 0.9.30-python3.12-bookworm-slim.
_VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)")
# In-house images: the GHCR releases (tag ${DOCFORGE_TAG}) and the local dev builds.
_IN_HOUSE = ("docforge-", "${", "ghcr.io/florian-barre/")
# Upstreams whose exact release is two numbers (postgres 16.15, seaweedfs 4.48).
_TWO_PART_RELEASES = ("postgres:", "chrislusf/seaweedfs:")


def _is_third_party(ref: str) -> bool:
    return not ref.startswith(_IN_HOUSE) and "${" not in ref and not ref.endswith(":dev")


def _problem(ref: str) -> str | None:
    match = _PINNED.match(ref)
    if not match:
        return f"{ref}: not `name:tag@sha256:<digest>`"
    version = _VERSION.match(match["tag"])
    parts = len(version[1].split(".")) if version else 0
    needed = 2 if ref.startswith(_TWO_PART_RELEASES) else 3
    if parts < needed:
        return f"{ref}: tag is not an exact version"
    return None


def test_the_scan_finds_the_files() -> None:
    assert len(_DOCKERFILES) >= 7
    assert any(path.name == "compose.base.yml" for path in _COMPOSE_FILES)


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_every_dockerfile_base_image_is_pinned(dockerfile: pathlib.Path) -> None:
    text = dockerfile.read_text(encoding="utf-8")
    stages = set(re.findall(r"^FROM\s.*\sAS\s+(\S+)", text, re.MULTILINE | re.IGNORECASE))
    refs = [ref for ref in _FROM.findall(text) if ref not in stages]
    assert refs, f"{dockerfile}: no FROM found"
    problems = [p for p in map(_problem, refs) if p]
    assert not problems, f"{dockerfile.relative_to(_REPO_ROOT)}: {problems}"


@pytest.mark.parametrize(
    "compose_file", _COMPOSE_FILES, ids=lambda p: str(p.relative_to(_REPO_ROOT))
)
def test_every_third_party_compose_image_is_pinned(compose_file: pathlib.Path) -> None:
    refs = list(filter(_is_third_party, _IMAGE.findall(compose_file.read_text(encoding="utf-8"))))
    problems = [p for p in map(_problem, refs) if p]
    assert not problems, f"{compose_file.relative_to(_REPO_ROOT)}: {problems}"


@pytest.mark.parametrize(
    ("ref", "pinned"),
    [
        ("python:3.12.16-slim-bookworm@sha256:" + "a" * 64, True),
        ("ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:" + "a" * 64, True),
        ("postgres:16.15-bookworm@sha256:" + "a" * 64, True),
        ("python:3.12-slim-bookworm@sha256:" + "a" * 64, False),
        ("ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:" + "a" * 64, False),
        ("gotenberg/gotenberg:8.39.0", False),
        ("postgres:16-bookworm@sha256:" + "a" * 64, False),
    ],
)
def test_the_pin_rule(ref: str, pinned: bool) -> None:
    assert (_problem(ref) is None) is pinned


@pytest.mark.parametrize(
    "ref",
    [
        "docforge-app:dev",
        "${COMPOSE_PROJECT_NAME:-docforge}-worker:dev",
        "ghcr.io/florian-barre/docforge-app:${DOCFORGE_TAG:-latest}",
        "ghcr.io/florian-barre/docforge-worker:1.2.3-cpu",
    ],
)
def test_in_house_images_need_no_digest(ref: str) -> None:
    assert not _is_third_party(ref)
