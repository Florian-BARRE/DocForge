# ====== Code Summary ======
# Coherence ratchet — .github/dependabot.yml must not propose what the uv projects cap on purpose.
# Dependabot does not read uv's `[tool.uv] constraint-dependencies`, so a package capped there
# (e.g. torch<2.14: cu126, the last CUDA index with sm_70 kernels, stops at torch 2.13) gets an
# unresolvable bump every week and the whole "Dependabot Updates" run goes red. Each `<X` cap must
# have a matching `>=X` ignore on that project's uv entry. Also checks that every
# `[[tool.uv.index]]` a uv project resolves from is declared as a Dependabot registry and listed on
# its entry (else the Dependabot proxy refuses the egress and every update of the project fails).
# And that every uv project and every Dockerfile of src/ has its entry (python image majors/minors
# ignored), and every project depending on torch/torchvision holds the V100 bound however it is
# pinned (`<` constraint or `==` in an extra). Serviceless: parses the TOML/YAML statically.

# ====== Standard Library Imports ======
import pathlib
import re
import tomllib
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
import yaml

# tests/units/coherence/<this> → parents[3] is src/docforge; its parents[1] is the repo root.
_SRC_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REPO_ROOT = _SRC_ROOT.parents[1]
_DEPENDABOT = _REPO_ROOT / ".github" / "dependabot.yml"

# Indexes Dependabot reaches without a registry entry (public, allow-listed by its proxy).
_PUBLIC_INDEX_HOSTS = ("download.pytorch.org", "pypi.org")

# The V100 rule (cu126 stops at torch 2.13): the ignore every torch-dependent project must carry.
_V100_BOUNDS = {"torch": ">=2.14", "torchvision": ">=0.29"}
_PYTHON_IMAGE_UPDATE_TYPES = {"version-update:semver-major", "version-update:semver-minor"}

_UPPER_CAP = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*<\s*([0-9][0-9A-Za-z.]*)\s*$")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _entries(ecosystem: str) -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(_DEPENDABOT.read_text(encoding="utf-8"))
    return {
        entry["directory"]: entry
        for entry in config["updates"]
        if entry["package-ecosystem"] == ecosystem
    }


def _uv_entries() -> dict[str, dict[str, Any]]:
    return _entries("uv")


def _ignored_versions(entry: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (_normalize(rule["dependency-name"]), version)
        for rule in entry.get("ignore", [])
        for version in rule.get("versions", [])
    }


def _repo_directory(path: pathlib.Path) -> str:
    return "/" + path.parent.relative_to(_REPO_ROOT).as_posix()


def _src_files(name: str) -> list[pathlib.Path]:
    return [
        path
        for path in (_REPO_ROOT / "src").rglob(name)
        if not {"node_modules", ".venv"}.intersection(path.parts)
    ]


def _pyproject(directory: str) -> dict[str, Any]:
    path = _REPO_ROOT / directory.lstrip("/") / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


_UV_DIRECTORIES = sorted(_uv_entries())


@pytest.mark.parametrize("directory", _UV_DIRECTORIES)
def test_every_uv_constraint_cap_is_ignored_by_dependabot(directory: str) -> None:
    constraints = (
        _pyproject(directory).get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
    )
    ignored = _ignored_versions(_uv_entries()[directory])
    caps = [m.groups() for m in map(_UPPER_CAP.match, constraints) if m]
    missing = [
        f"{name}>={bound}"
        for name, bound in caps
        if (_normalize(name), f">={bound}") not in ignored
    ]
    assert not missing, (
        f"{directory}: capped in [tool.uv] constraint-dependencies but not ignored in "
        f'.github/dependabot.yml (add `versions: [">=X"]` ignore rules): {missing}'
    )


@pytest.mark.parametrize("directory", _UV_DIRECTORIES)
def test_every_private_uv_index_is_a_dependabot_registry(directory: str) -> None:
    config = yaml.safe_load(_DEPENDABOT.read_text(encoding="utf-8"))
    registries = config.get("registries", {})
    listed = set(_uv_entries()[directory].get("registries", []))
    indexes = _pyproject(directory).get("tool", {}).get("uv", {}).get("index", [])
    problems = []
    for index in indexes:
        url = index["url"]
        if any(host in url for host in _PUBLIC_INDEX_HOSTS):
            continue
        names = [
            name
            for name, registry in registries.items()
            if registry.get("type") == "python-index"
            and registry.get("url", "").rstrip("/") == url.rstrip("/")
        ]
        if not names:
            problems.append(f"{url}: no python-index registry with this url")
        elif not listed.intersection(names):
            problems.append(f"{url}: registry {names} not listed on the entry")
    assert not problems, f"{directory}: {problems}"


def test_every_uv_project_has_a_dependabot_entry() -> None:
    projects = {_repo_directory(lock) for lock in _src_files("uv.lock")}
    missing = sorted(projects - set(_UV_DIRECTORIES))
    assert not missing, f"uv projects without a `uv` entry in .github/dependabot.yml: {missing}"


def test_every_dockerfile_has_a_dependabot_entry_holding_python() -> None:
    entries = _entries("docker")
    problems = []
    for directory in sorted({_repo_directory(path) for path in _src_files("Dockerfile")}):
        entry = entries.get(directory)
        if entry is None:
            problems.append(f"{directory}: no `docker` entry")
            continue
        held = {
            update_type
            for rule in entry.get("ignore", [])
            if rule["dependency-name"] == "python"
            for update_type in rule.get("update-types", [])
        }
        if not _PYTHON_IMAGE_UPDATE_TYPES <= held:
            problems.append(f"{directory}: python image majors/minors not ignored")
    assert not problems, problems


@pytest.mark.parametrize("directory", _UV_DIRECTORIES)
def test_torch_dependent_projects_hold_the_v100_bound(directory: str) -> None:
    project = _pyproject(directory).get("project", {})
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    names = {_normalize(re.split(r"[\s\[<>=!~;]", req, maxsplit=1)[0]) for req in requirements}
    ignored = _ignored_versions(_uv_entries()[directory])
    missing = [
        f"{name}{bound}"
        for name, bound in _V100_BOUNDS.items()
        if name in names and (name, bound) not in ignored
    ]
    assert not missing, f"{directory}: depends on torch but .github/dependabot.yml misses {missing}"
