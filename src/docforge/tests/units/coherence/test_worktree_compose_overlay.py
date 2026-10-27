# ====== Code Summary ======
# Coherence ratchet — the per-worktree dev overlay (compose/overlays/compose.worktree.yml) must keep
# isolating each git worktree's dev stack from the main checkout's one. Layered on top of
# compose.dev-cpu.yml (which includes compose.base.yml + overlays/compose.dev.yml), it must:
#   * reset `container_name` on EVERY service that base/dev pins one on (else two stacks collide);
#   * name every image built from source after the compose project (${COMPOSE_PROJECT_NAME:-docforge}),
#     so a worktree's build never replaces the image main or another worktree runs, while main's
#     project ("docforge") keeps dev's names;
#   * reset the host ports of every service, except frontend / app / mcp which publish on
#     ${BIND_ADDR:-127.0.0.1} with a port variable (APP_PORT — the UI is the app of
#     scripts/dev-stack.sh — / API_PORT / MCP_PORT);
#   * start the core services by default (no profile, Vite frontend included), the CPU model hosts
#     under `models`, mcp under `extras`;
#   * never pin a `name:` on volumes or networks, nor let base/dev pin one (the overlay cannot undo
#     it, so they must stay project-scoped);
#   * reach seaweedfs's S3 through the project-scoped network alias `seaweedfs` (app and worker),
#     and make app and worker wait for seaweedfs:8333 before starting (survives a host reboot,
#     where the Docker daemon restarts every container at once and ignores depends_on).
# A service added to base/dev with a container_name or host ports goes red here until the worktree
# overlay handles it. Serviceless: parses the YAML statically (Compose's !reset / !override tags are
# recorded, not interpreted) and never shells out to docker. scripts/dev-stack.sh, which drives the
# overlay, must stay executable in the git index and syntactically valid bash, and must look for the
# kit's port-slot tool in the account only (~/.aidk/bin), never in the kit v1's machine-wide install.

# ====== Standard Library Imports ======
import pathlib
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
import yaml

# tests/units/coherence/<this> → parents[3] is src/docforge; its parents[1] is the repo root.
_SRC_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REPO_ROOT = _SRC_ROOT.parents[1]
_COMPOSE_DIR = _REPO_ROOT / "compose"
_BASE = _COMPOSE_DIR / "compose.base.yml"
_DEV = _COMPOSE_DIR / "overlays" / "compose.dev.yml"
_WORKTREE = _COMPOSE_DIR / "overlays" / "compose.worktree.yml"
_DEV_STACK = _REPO_ROOT / "scripts" / "dev-stack.sh"

# The services a browser reaches from the host, and the port variable each one reads.
_PUBLISHED = {
    "docforge_frontend": "APP_PORT",
    "docforge_app": "API_PORT",
    "docforge_mcp": "MCP_PORT",
}
_CORE = (
    "docforge_frontend",
    "docforge_app",
    "docforge_worker",
    "docforge_postgres",
    "docforge_redis",
    "docforge_qdrant",
    "docforge_seaweedfs",
    "docforge_gotenberg",
)
_MODELS = ("docforge_bge_server", "docforge_paddle_server")
_EXTRAS = ("docforge_mcp",)


@dataclass(frozen=True)
class _Tagged:
    """A Compose custom-tagged node (`!reset` / `!override`) with its tag and plain value."""

    tag: str
    value: Any


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that records Compose's !reset / !override tags instead of failing on them."""


def _construct_tagged(loader: yaml.SafeLoader, node: yaml.Node) -> _Tagged:
    if isinstance(node, yaml.MappingNode):
        value: Any = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)
        if node.tag == "!reset" and value in ("", "null", "~"):
            value = None
    return _Tagged(tag=node.tag, value=value)


for _tag in ("!reset", "!override"):
    _ComposeLoader.add_constructor(_tag, _construct_tagged)


def _load(path: pathlib.Path) -> dict[str, Any]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}


def _services(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {name: (svc or {}) for name, svc in (_load(path).get("services") or {}).items()}


@pytest.fixture(scope="module")
def upstream() -> dict[str, list[dict[str, Any]]]:
    """Each service of base + dev, mapped to its definitions (in layering order)."""
    merged: dict[str, list[dict[str, Any]]] = {}
    for path in (_BASE, _DEV):
        for name, svc in _services(path).items():
            merged.setdefault(name, []).append(svc)
    return merged


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return _load(_WORKTREE)


@pytest.fixture(scope="module")
def overlay_services(overlay: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: (svc or {}) for name, svc in (overlay.get("services") or {}).items()}


def _effective_profiles(
    name: str,
    upstream: dict[str, list[dict[str, Any]]],
    overlay_services: dict[str, dict[str, Any]],
) -> list[str]:
    """Profiles after layering the overlay: an overlay !reset / !override replaces upstream's."""
    svc = overlay_services.get(name, {})
    if "profiles" in svc:
        value = svc["profiles"]
        if isinstance(value, _Tagged):
            return list(value.value or [])
        return sorted({*_upstream_profiles(name, upstream), *value})
    return _upstream_profiles(name, upstream)


def _upstream_profiles(name: str, upstream: dict[str, list[dict[str, Any]]]) -> list[str]:
    return sorted({p for svc in upstream.get(name, []) for p in svc.get("profiles") or []})


# ── container_name ───────────────────────────────────────────────────────────────


def test_upstream_pins_container_names_so_the_ratchet_is_live(upstream):
    """Sanity: base/dev do pin container names — otherwise the ratchet below checks nothing."""
    assert any("container_name" in svc for defs in upstream.values() for svc in defs)


def test_every_upstream_container_name_is_reset_in_the_worktree_overlay(upstream, overlay_services):
    pinned = sorted(
        name for name, defs in upstream.items() if any("container_name" in svc for svc in defs)
    )
    not_reset = [
        name
        for name in pinned
        if overlay_services.get(name, {}).get("container_name") != _Tagged("!reset", None)
    ]
    assert not not_reset, (
        f"services pinning a container_name in base/dev without `container_name: !reset null` in "
        f"{_WORKTREE.name}: {not_reset}"
    )


def test_overlay_sets_no_container_name_of_its_own(overlay_services):
    offenders = [
        name
        for name, svc in overlay_services.items()
        if "container_name" in svc and svc["container_name"] != _Tagged("!reset", None)
    ]
    assert not offenders, f"overlay must only reset container_name, never set one: {offenders}"


def test_overlay_only_targets_services_defined_upstream(upstream, overlay_services):
    unknown = sorted(set(overlay_services) - set(upstream))
    assert not unknown, f"overlay services absent from base/dev (typo or stale entry): {unknown}"


# ── images ───────────────────────────────────────────────────────────────────────

_PROJECT_VAR = "${COMPOSE_PROJECT_NAME:-docforge}"


def _built_upstream_images(upstream: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    """Each service base/dev builds from source, mapped to its (last-defined) image name."""
    built: dict[str, str] = {}
    for name, defs in upstream.items():
        if any("build" in svc for svc in defs):
            images = [svc["image"] for svc in defs if "image" in svc]
            built[name] = images[-1] if images else ""
    return built


def test_upstream_builds_images_so_the_ratchet_is_live(upstream):
    """Sanity: base/dev do build images under a fixed dev name — else the ratchet checks nothing."""
    assert _built_upstream_images(upstream).get("docforge_app") == "docforge-app:dev"


def test_every_built_image_is_named_after_the_compose_project(upstream, overlay_services):
    """A worktree's build must not overwrite main's (or another worktree's) image."""
    built = _built_upstream_images(upstream)
    wrong = {
        name: overlay_services.get(name, {}).get("image")
        for name in sorted(built)
        if not str(overlay_services.get(name, {}).get("image", "")).startswith(_PROJECT_VAR + "-")
    }
    assert not wrong, (
        f"services built from source without an image named `{_PROJECT_VAR}-<name>:<tag>` in "
        f"{_WORKTREE.name}: {wrong}"
    )


def test_main_keeps_the_dev_image_names(upstream, overlay_services):
    """Main runs as project "docforge": the overlay must resolve there to dev's very names."""
    drift = {}
    for name, dev_image in sorted(_built_upstream_images(upstream).items()):
        image = str(overlay_services.get(name, {}).get("image", ""))
        if image.replace(_PROJECT_VAR, "docforge", 1) != dev_image:
            drift[name] = (image, dev_image)
    assert not drift, f"overlay image, with the project `docforge`, differs from dev's: {drift}"


# ── ports ────────────────────────────────────────────────────────────────────────


def test_every_upstream_service_with_ports_is_handled_by_the_overlay(upstream, overlay_services):
    with_ports = sorted(
        name for name, defs in upstream.items() if any("ports" in svc for svc in defs)
    )
    unhandled = [name for name in with_ports if "ports" not in overlay_services.get(name, {})]
    assert not unhandled, f"services publishing host ports not reset in the overlay: {unhandled}"


def test_unpublished_services_have_their_ports_reset_to_empty(overlay_services):
    offenders = {
        name: svc["ports"]
        for name, svc in overlay_services.items()
        if name not in _PUBLISHED and "ports" in svc and svc["ports"] != _Tagged("!reset", [])
    }
    assert not offenders, f"only app/frontend/mcp may publish host ports, got: {offenders}"


@pytest.mark.parametrize(("service", "port_var"), sorted(_PUBLISHED.items()))
def test_published_service_binds_bind_addr_and_its_port_variable(
    service, port_var, overlay_services
):
    ports = overlay_services.get(service, {}).get("ports")
    assert isinstance(ports, _Tagged) and ports.tag == "!override", (
        f"{service}: ports must be `!override` so upstream's fixed ports are dropped, got {ports!r}"
    )
    assert ports.value, f"{service}: overlay publishes no port"
    pattern = re.compile(r"^\$\{BIND_ADDR:-127\.0\.0\.1\}:\$\{" + port_var + r"(?::-\d+)?\}:\d+$")
    bad = [p for p in ports.value if not (isinstance(p, str) and pattern.match(p))]
    assert not bad, (
        f"{service}: ports not bound to ${{BIND_ADDR:-127.0.0.1}}:${{{port_var}}}: {bad}"
    )


# ── profiles ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("service", _CORE)
def test_core_service_has_no_profile(service, upstream, overlay_services):
    assert service in upstream, f"{service} no longer defined in base/dev"
    assert _effective_profiles(service, upstream, overlay_services) == []


@pytest.mark.parametrize("service", _MODELS)
def test_model_host_is_in_the_models_profile_only(service, upstream, overlay_services):
    assert service in upstream, f"{service} no longer defined in base/dev"
    assert _effective_profiles(service, upstream, overlay_services) == ["models"]


@pytest.mark.parametrize("service", _EXTRAS)
def test_extra_service_is_in_the_extras_profile_only(service, upstream, overlay_services):
    assert service in upstream, f"{service} no longer defined in base/dev"
    assert _effective_profiles(service, upstream, overlay_services) == ["extras"]


# ── volumes / networks ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("section", ["volumes", "networks"])
def test_overlay_pins_no_name_on_volumes_or_networks(section, overlay):
    pinned = [
        key
        for key, spec in (overlay.get(section) or {}).items()
        if isinstance(spec, dict) and "name" in spec
    ]
    assert not pinned, (
        f"overlay {section} with a fixed `name:` would be shared across worktrees: {pinned}"
    )


@pytest.mark.parametrize("path", [_BASE, _DEV], ids=["base", "dev"])
@pytest.mark.parametrize("section", ["volumes", "networks"])
def test_upstream_pins_no_name_on_volumes_or_networks(section, path):
    """A fixed `name:` in base/dev would be shared by every stack, and the overlay can't undo it."""
    pinned = [
        key
        for key, spec in (_load(path).get(section) or {}).items()
        if isinstance(spec, dict) and "name" in spec
    ]
    assert not pinned, (
        f"{path.name} {section} with a fixed `name:` would be shared across worktrees: {pinned}"
    )


# ── S3 endpoint ──────────────────────────────────────────────────────────────────


def test_seaweedfs_has_the_seaweedfs_network_alias(overlay_services):
    networks = overlay_services.get("docforge_seaweedfs", {}).get("networks")
    assert isinstance(networks, dict), f"docforge_seaweedfs: no networks mapping, got {networks!r}"
    aliased = [
        net for net, spec in networks.items() if "seaweedfs" in ((spec or {}).get("aliases") or [])
    ]
    assert aliased, "docforge_seaweedfs: no `seaweedfs` network alias (botocore-valid S3 hostname)"


@pytest.mark.parametrize("service", ["docforge_app", "docforge_worker"])
def test_s3_endpoint_points_at_the_seaweedfs_alias(service, overlay_services):
    env = overlay_services.get(service, {}).get("environment")
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env if "=" in item)
    assert isinstance(env, dict), f"{service}: no environment in the overlay, got {env!r}"
    assert env.get("S3_ENDPOINT_URL") == "http://seaweedfs:8333"


@pytest.mark.parametrize("service", ["docforge_app", "docforge_worker"])
def test_app_and_worker_wait_for_s3_before_starting(service, overlay_services):
    """After a host reboot the daemon ignores depends_on: the command itself must wait for S3."""
    command = overlay_services.get(service, {}).get("command")
    assert isinstance(command, _Tagged) and command.tag == "!override", (
        f"{service}: command must be `!override` (wait for S3, then the dev command), got {command!r}"
    )
    assert command.value[:2] == ["sh", "-c"], f"{service}: command must be `sh -c ...`"
    script = command.value[2]
    assert '"http://seaweedfs:8333/"' in script and 'exec "$$@"' in script, (
        f"{service}: command does not wait for seaweedfs:8333 then exec the dev command"
    )
    # PID 1 sh ignores SIGTERM without a handler: `docker stop` would wait out its grace period.
    assert script.lstrip().startswith("trap 'exit 143' TERM INT"), (
        f"{service}: the S3 wait must start with a SIGTERM/SIGINT trap"
    )
    assert command.value[3] == "sh", (
        f"{service}: the script's $0 must be `sh` (args after it are $@)"
    )
    dev_cmd = _services(_DEV).get(service, {}).get("command")
    if isinstance(dev_cmd, str):
        dev_cmd = shlex.split(dev_cmd)
    assert dev_cmd and command.value[4:] == dev_cmd, (
        f"{service}: the command run after the S3 wait drifted from overlays/compose.dev.yml "
        f"({command.value[4:]!r} != {dev_cmd!r})"
    )


# ── scripts/dev-stack.sh ─────────────────────────────────────────────────────────


@pytest.mark.skipif(
    shutil.which("git") is None or not (_REPO_ROOT / ".git").exists(),
    reason="not a git checkout",
)
def test_dev_stack_script_is_executable_in_the_git_index():
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "-s", "--", "scripts/dev-stack.sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.stdout.strip():
        pytest.skip("scripts/dev-stack.sh not tracked in this checkout")
    assert result.stdout.split()[0] == "100755"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_dev_stack_script_is_valid_bash():
    if not _DEV_STACK.is_file():
        pytest.skip("scripts/dev-stack.sh absent")
    result = subprocess.run(
        ["bash", "-n", str(_DEV_STACK)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_dev_stack_script_does_not_call_the_kit_v1():
    kit_v1_dir = "/".join(("", "opt", "aidk"))  # spelled apart so the repository never names it
    assert kit_v1_dir not in _DEV_STACK.read_text(encoding="utf-8")
