# ====== Code Summary ======
# Unit tests for CapabilitiesService.describe(): the deployment-capability matrix must reflect which
# optional sidecars are reachable (a parser/ocr/embed kind that needs a sidecar appears ONLY when that
# sidecar's probe passes), in-worker kinds are always present, and gpu_present derives from a reachable
# sidecar advertising a "cuda" device. The sidecar probe is faked (no network) so the logic is asserted
# offline. `backend` imports are deferred into the tests: the api-dir autouse fixture boots the app
# (inserting app/ on sys.path) before any test body runs — importing `backend` at module scope would
# fail at collection time, before that fixture.

# ====== Standard Library Imports ======
import asyncio
from types import SimpleNamespace

# The five optional sidecars CapabilitiesService probes (keys the fake probe must answer for).
_SIDECAR_NAMES = ["gotenberg", "bge_server", "paddle_server", "mineru_server", "dots_ocr_server"]


def _config(*, auth_enabled: bool = False) -> SimpleNamespace:
    """A minimal stand-in for RUNTIME_CONFIG carrying only what describe() reads."""
    return SimpleNamespace(
        FASTAPI_APP_VERSION="test",
        AUTH_ENABLED=auth_enabled,
        CAPABILITIES_BGE_SERVER_URL="http://bge_server:80",
        CAPABILITIES_PADDLE_SERVER_URL="http://paddle_server:80",
        CAPABILITIES_MINERU_SERVER_URL="http://mineru_server:80",
        CAPABILITIES_DOTS_OCR_SERVER_URL="http://dots_ocr_server:80",
        CAPABILITIES_GOTENBERG_URL="http://gotenberg:3000",
        POSTGRES_DSN="postgresql://x",
        QDRANT_URL="http://qdrant:6333",
        REDIS_URL="redis://redis:6379/0",
        S3_ENDPOINT_URL="http://seaweedfs:8333",
    )


def _fake_probe(reachable: dict[str, bool], devices: dict[str, str] | None = None):
    """Build a probe object with an async ``probe`` returning a canned per-sidecar reachability map."""
    from backend.libs.capabilities.probe import ProbeResult  # noqa: PLC0415 — deferred (see header)

    devices = devices or {}

    class _FakeProbe:
        async def probe(self, targets: dict[str, str]) -> dict:
            return {
                name: ProbeResult(
                    reachable=reachable.get(name, False),
                    device=devices.get(name),
                    detail=None if reachable.get(name, False) else "unreachable",
                )
                for name in _SIDECAR_NAMES
            }

    return _FakeProbe()


def _describe(
    reachable: dict[str, bool],
    devices: dict[str, str] | None = None,
    *,
    auth_enabled: bool = False,
):
    """Run the async describe() to a CapabilitiesResponse with a faked probe."""
    from backend.libs.capabilities.service import CapabilitiesService  # noqa: PLC0415 — deferred

    service = CapabilitiesService(
        _config(auth_enabled=auth_enabled), _fake_probe(reachable, devices)
    )
    return asyncio.run(service.describe())


def test_auth_enabled_mirrors_runtime_config() -> None:
    """B1 — /capabilities.auth_enabled must be the DEPLOYMENT's real AUTH_ENABLED, not a UI guess.

    The UI dresses the whole key/token surface as protective; on an AUTH_ENABLED=false deployment
    that is a false sense of security, so the frontend needs the true auth state to warn. It is
    derived straight from RUNTIME_CONFIG — never a literal — so it flips with the config.
    """
    assert _describe({}, auth_enabled=False).auth_enabled is False
    assert _describe({}, auth_enabled=True).auth_enabled is True


def test_sidecar_backed_parsers_appear_only_when_their_sidecar_is_reachable() -> None:
    """paddle_server reachable + mineru/dots unreachable → pp_structure/paddleocr_vl in, mineru/dots out."""
    parsers = _describe(
        {"paddle_server": True, "bge_server": True, "gotenberg": True}
    ).capabilities.parsers
    # In-worker parser is ALWAYS available; the paddle sidecar's parsers are in (it is reachable).
    assert "docling" in parsers
    assert "pp_structure" in parsers and "paddleocr_vl" in parsers
    # Their sidecars are unreachable here → these must NOT be advertised as available.
    assert "mineru" not in parsers
    assert "dots_ocr" not in parsers


def test_mineru_and_dots_appear_once_their_sidecars_are_reachable() -> None:
    """Flip the mineru/dots sidecars reachable → their parser kinds become available."""
    parsers = _describe(
        {"mineru_server": True, "dots_ocr_server": True, "paddle_server": True}
    ).capabilities.parsers
    assert "mineru" in parsers
    assert "dots_ocr" in parsers


def test_gpu_present_derives_from_a_reachable_cuda_sidecar() -> None:
    """gpu_present is True iff some reachable sidecar advertises device 'cuda'; None when no device info."""
    on_cuda = _describe({"bge_server": True}, devices={"bge_server": "cuda"})
    assert on_cuda.gpu_present is True

    no_device = _describe({"bge_server": True})  # reachable but advertises no device
    assert no_device.gpu_present is None


def test_unreachable_sidecar_is_still_listed_in_services() -> None:
    """An off/unreachable sidecar is reported (reachable=False) — the operator sees it exists but is off."""
    resp = _describe({"paddle_server": True})
    mineru = next(s for s in resp.services if s.name == "mineru_server")
    assert mineru.reachable is False
    assert "parser:mineru" in mineru.provides


def test_ocr_embed_rerank_gating_follows_their_sidecars() -> None:
    """paddle → ocr:paddle available; bge → embed:bge_server + rerank:cross_encoder available; else not."""
    with_both = _describe({"paddle_server": True, "bge_server": True})
    assert "paddle" in with_both.capabilities.ocr
    assert "bge_server" in with_both.capabilities.embed
    assert "cross_encoder" in with_both.capabilities.rerank
    # In-worker OCR is always there; the sidecar OCR is gated on paddle_server.
    assert "rapidocr" in with_both.capabilities.ocr and "tesseract" in with_both.capabilities.ocr

    without = _describe({})  # no sidecar reachable
    assert "paddle" not in without.capabilities.ocr
    assert "bge_server" not in without.capabilities.embed
    assert without.capabilities.rerank == []  # cross_encoder needs bge_server
    assert "rapidocr" in without.capabilities.ocr  # in-worker survives


def test_gpu_present_false_when_reachable_sidecars_are_cpu_only() -> None:
    """A reachable sidecar advertising 'cpu' (no cuda anywhere) yields gpu_present False, not None."""
    resp = _describe({"bge_server": True}, devices={"bge_server": "cpu"})
    assert resp.gpu_present is False


def test_every_matrix_kind_is_gated_or_declared_in_worker() -> None:
    """RATCHET — every selectable registry kind of a matrix family must be classified.

    Each ``family:kind`` the capability matrix can surface must be EITHER sidecar-gated
    (``SIDECARS.provides``) OR declared in-worker/cloud (``IN_WORKER_OR_CLOUD``). A newly-added
    provider that skips this classification would default to "always available" — silently
    advertising a sidecar-hosted kind even when its sidecar is down. This fails the moment such a
    kind appears, forcing the gating decision (see requirements.py).
    """
    from backend.libs.capabilities.requirements import (  # noqa: PLC0415 — deferred (see header)
        FAMILY_MAP,
        IN_WORKER_OR_CLOUD,
        SIDECARS,
    )
    from shared_libs.pipelines.registry import NodeRegistry  # noqa: PLC0415

    classified = {cap for sidecar in SIDECARS for cap in sidecar.provides} | IN_WORKER_OR_CLOUD
    unclassified = sorted(
        f"{family}:{card.kind}"
        for family in FAMILY_MAP.values()
        if family in NodeRegistry.families()
        for card in NodeRegistry.catalog(family)
        # Exclude the test/fake node doubles sibling unit tests register into the process-global
        # NodeRegistry — they are fixtures, not product surface (mirrors tests/units/coherence).
        if not card.kind.startswith(("test_", "fake_"))
        if f"{family}:{card.kind}" not in classified
    )
    assert not unclassified, (
        f"capability kinds neither sidecar-gated nor declared in-worker/cloud: {unclassified}. "
        "Add each to SIDECARS.provides (a sidecar hosts it) or IN_WORKER_OR_CLOUD (in-worker/cloud) "
        "in app/backend/libs/capabilities/requirements.py."
    )
