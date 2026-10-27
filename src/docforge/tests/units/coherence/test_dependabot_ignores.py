# ====== Code Summary ======
# Coherence ratchet — .github/dependabot.yml must not propose what the uv projects cap on purpose.
# Dependabot does not read uv's `[tool.uv] constraint-dependencies`, so a package capped there
# (e.g. torch<2.14: cu126, the last CUDA index with sm_70 kernels, stops at torch 2.13) gets an
# unresolvable bump every week and the whole "Dependabot Updates" run goes red. Each `<X` cap must
# have a matching `>=X` ignore on that project's uv entry. Also checks that every
# `[[tool.uv.index]]` a uv project resolves from is declared as a Dependabot registry and listed on
# its entry (else the Dependabot proxy refuses the egress and every update of the project fails).
# Serviceless: parses the TOML/YAML statically.

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

_UPPER_CAP = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*<\s*([0-9][0-9A-Za-z.]*)\s*$")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _uv_entries() -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(_DEPENDABOT.read_text(encoding="utf-8"))
    return {
        entry["directory"]: entry
        for entry in config["updates"]
        if entry["package-ecosystem"] == "uv"
    }


def _pyproject(directory: str) -> dict[str, Any]:
    path = _REPO_ROOT / directory.lstrip("/") / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


_UV_DIRECTORIES = sorted(_uv_entries())


@pytest.mark.parametrize("directory", _UV_DIRECTORIES)
def test_every_uv_constraint_cap_is_ignored_by_dependabot(directory: str) -> None:
    constraints = (
        _pyproject(directory).get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
    )
    ignored = {
        (_normalize(rule["dependency-name"]), version)
        for rule in _uv_entries()[directory].get("ignore", [])
        for version in rule.get("versions", [])
    }
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
