"""Doc↔code coherence ratchets — the mechanical guard against divergence-doc rot.

The 2026-09 full audit's single largest finding class was documentation divergence: code moved,
the living docs (PIPELINE.md, docs/, CLAUDE.md) did not. These tests turn the cheap, objective
slices of that contract into CI-enforced invariants, so the drift is caught at the gate instead of
by the next audit:

  * every registered INGEST node kind must appear (as a literal, grep-able string) in PIPELINE.md —
    the living pipeline reference. This is exactly the "PIPELINE.md inventory drift" finding, now a
    ratchet. (On first landing, this immediately caught the undocumented ``metagen_skip``.)
  * the seven stage names must appear in PIPELINE.md.
  * repo-path references in the tracked top-level docs (docs/*.md, PIPELINE.md, README.md) must
    point at files/dirs that exist — a rename that forgets its doc ripple goes red here.
  * every compose file must keep the ``compose.*.yml`` naming (the Dependabot docker-compose glob):
    a new scenario/overlay added under the old bare naming would silently lose dependency coverage.
  * CLAUDE.md's referenced compose/script paths must exist — LOCAL-ONLY (CLAUDE.md is gitignored,
    absent on CI, so the test skips there; a dev run still enforces it).

Deliberately narrow: only objective, string-level facts are checked (a kind name, a path, a stage
token). Prose accuracy stays a human/review concern — see .claude/rules/methodology.md.
"""

import pathlib
import re

import pytest

from shared_libs.pipelines.ingest.pipeline import IngestPipeline
from shared_libs.pipelines.ingest.stages import (
    IngestAssembler,  # noqa: F401 — imports register every node
)
from shared_libs.pipelines.registry import NodeRegistry

# src/docforge/ (this uv project's root — PIPELINE.md lives here).
_SRC_ROOT = pathlib.Path(__file__).resolve().parents[3]
# The monorepo root (docs/, README.md, compose/, CLAUDE.md live here).
_REPO_ROOT = _SRC_ROOT.parents[1]

# Path-like references we deliberately tolerate as absent (illustrative examples in prose).
# Add here ONLY with a reason; an unexplained dead path must be fixed in the doc, not allowlisted.
_DEAD_PATH_EXCEPTIONS: frozenset[str] = frozenset()

# Matches backticked repo paths in prose: `src/...`, `compose/...`, `scripts/...`, `services/...`.
# Placeholders (<>, {}, *, …) never match, so templated examples are naturally excluded.
_PATH_REF = re.compile(r"`((?:src|compose|scripts|services)/[A-Za-z0-9_.\-/]+)`")

_STAGES = ("INTAKE", "PARSE", "ENRICH", "CHUNK", "CONTEXTUALIZE", "METAGEN", "EMBED")


def _pipeline_md() -> str:
    return (_SRC_ROOT / "PIPELINE.md").read_text(encoding="utf-8")


def _ingest_palette_kinds() -> list[tuple[str, str]]:
    """The (family, kind) pairs the INGEST palette actually exposes.

    Mirrors the pipeline's own scoping: shared families (``deliver``) are restricted through
    ``IngestPipeline.FAMILY_KINDS`` (so search's ``hits`` never leaks in), and test doubles that
    sibling unit tests register into the process-global ``NodeRegistry`` (``test_*``/``fake_*``
    kinds) are excluded — they are fixtures, not product surface.
    """
    pairs = []
    for family in IngestPipeline.FAMILIES:
        if family not in NodeRegistry.families():
            continue
        allowed = IngestPipeline.FAMILY_KINDS.get(family)
        for kind in NodeRegistry.kinds(family):
            if kind.startswith(("test_", "fake_")):
                continue
            if allowed is not None and kind not in allowed:
                continue
            pairs.append((family, kind))
    return pairs


def test_every_ingest_node_kind_is_documented_in_pipeline_md() -> None:
    """Every kind of every family the ingest pipeline assembles from appears literally in
    PIPELINE.md — adding a node without documenting it (or renaming one without the doc ripple)
    fails here, at the gate, instead of surfacing as audit rot months later."""
    text = _pipeline_md()
    missing = [f"{family}/{kind}" for family, kind in _ingest_palette_kinds() if kind not in text]
    assert not missing, (
        f"Registered ingest node kind(s) absent from src/docforge/PIPELINE.md: {missing}. "
        f"PIPELINE.md is the living pipeline reference — document the kind (a literal, grep-able "
        f"mention) in the same change that adds or renames it."
    )


def test_pipeline_md_documents_all_seven_stages() -> None:
    """The seven canonical stage names stay present — a stage rename/restructure must carry its
    doc ripple in the same change."""
    text = _pipeline_md()
    missing = [stage for stage in _STAGES if stage not in text]
    assert not missing, f"Stage name(s) absent from PIPELINE.md: {missing}"


def _dead_refs_in(path: pathlib.Path) -> list[str]:
    """Backticked repo-path references in ``path`` that point at nothing on disk."""
    dead = []
    for match in _PATH_REF.finditer(path.read_text(encoding="utf-8")):
        ref = match.group(1).rstrip("/").rstrip(".")
        if ref in _DEAD_PATH_EXCEPTIONS:
            continue
        if not (_REPO_ROOT / ref).exists():
            dead.append(f"{path.relative_to(_REPO_ROOT)}: `{ref}`")
    return dead


def test_tracked_docs_path_references_exist() -> None:
    """Every backticked src/compose/scripts/services path in the tracked top-level docs exists.
    docs/archive/ is deliberately excluded (frozen legacy prose). A rename that forgets its doc
    ripple — the audit's compose-rename class — goes red here."""
    docs = sorted((_REPO_ROOT / "docs").glob("*.md"))
    docs += [_SRC_ROOT / "PIPELINE.md", _REPO_ROOT / "README.md"]
    dead = [ref for doc in docs if doc.exists() for ref in _dead_refs_in(doc)]
    assert not dead, (
        "Dead repo-path reference(s) in tracked docs — update the doc in the same change that "
        f"moved/removed the path (or, for a deliberate prose example, add it to "
        f"_DEAD_PATH_EXCEPTIONS with a reason): {dead}"
    )


def test_compose_files_keep_the_dependabot_covered_naming() -> None:
    """Every compose YAML keeps the ``compose.*.yml`` name so Dependabot's docker-compose glob
    keeps scanning its image pins. A new scenario/overlay added under the old bare naming would
    silently lose dependency coverage (the exact gap audit finding 583 closed)."""
    offenders = [
        str(p.relative_to(_REPO_ROOT))
        for p in (_REPO_ROOT / "compose").rglob("*.yml")
        if not p.name.startswith("compose.") and p.name != "README.md"
    ]
    assert not offenders, (
        f"Compose file(s) outside the Dependabot-covered `compose.*.yml` naming: {offenders}"
    )


@pytest.mark.skipif(
    not (_REPO_ROOT / "CLAUDE.md").exists(),
    reason="CLAUDE.md is gitignored (local-only); nothing to check on CI",
)
def test_claude_md_referenced_paths_exist() -> None:
    """LOCAL ratchet: the command matrix in the root CLAUDE.md must reference paths that exist —
    a stale CLAUDE.md command misleads every future session (the audit's `/dev`-skill class)."""
    dead = _dead_refs_in(_REPO_ROOT / "CLAUDE.md")
    assert not dead, f"CLAUDE.md references dead path(s) — fix the command matrix: {dead}"
