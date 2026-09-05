"""Frozen golden of the stock ingestion blob — locks the default topology byte-for-byte.

The "byte-identical default" guarantee that lets every phase evolve the pipeline without silently
drifting the stock blob is pinned HERE: a single checked-in snapshot of
``IngestAssembler.assemble(default_state()).model_dump(mode="json")``. If a change to the assembler,
the state defaults or any stage builder alters the default blob, this test fails loudly and the
snapshot must be regenerated ON PURPOSE (never blindly). To regenerate after an intended change:
``fixtures/default_blob.json`` = json.dumps(blob.model_dump(mode="json"), sort_keys=True, indent=2)
(pretty-printed so its diff stays readable — the test compares dicts, so the layout is cosmetic).

A SECOND lock ties that shape to ``ENGINE_BLOB_VERSION``: a shape change that keeps a stale version
number lets already-stored blobs wrongly fast-path as "current" (the exact bug the v1→v2 comment in
``normalizer.py`` records — the source_probe wiring shipped without a bump). The version-lock test
turns that silent miss into a failing test, so the bump can never be forgotten again.
"""

import hashlib
import json
import pathlib

from shared_libs.pipelines.ingest.stages import IngestAssembler, default_state
from shared_libs.pipelines.ingest.stages.normalizer import ENGINE_BLOB_VERSION

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"
_GOLDEN = _FIXTURES / "default_blob.json"
_VERSION_LOCK = _FIXTURES / "default_blob_version.json"


def _default_blob() -> dict:
    """Assemble the stock blob exactly as ``IngestPipeline.default_blob`` (the stored default) does."""
    return IngestAssembler.assemble(default_state()).model_dump(mode="json")


def _shape_hash(blob: dict) -> str:
    """A stable structural fingerprint of a blob — canonical (key-sorted, tight) JSON, sha256."""
    canonical = json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def test_default_blob_matches_the_frozen_golden() -> None:
    expected = json.loads(_GOLDEN.read_text())
    actual = _default_blob()
    assert actual == expected


def test_default_blob_shape_change_forces_engine_version_bump() -> None:
    """A stock-blob shape change is only allowed together with an ENGINE_BLOB_VERSION bump.

    The version-lock fixture freezes the ``(engine_blob_version, blob_sha256)`` pair last committed.
    The gate runs off that pair:

    1. Shape unchanged since the freeze → nothing to enforce (but the frozen version must still
       equal the code's version — they move together).
    2. Shape changed while ENGINE_BLOB_VERSION stayed put → FAIL: the bump was forgotten, and
       stored blobs would fast-path stale (the source_probe-class regression).
    3. Shape changed AND the version was bumped → the change is legitimate, but the fixture is now
       stale → FAIL asking for its regeneration so the new pair is frozen.
    """
    # 1. Compare the live shape against the frozen fingerprint.
    record = json.loads(_VERSION_LOCK.read_text())
    frozen_version = record["engine_blob_version"]
    frozen_hash = record["blob_sha256"]
    current_hash = _shape_hash(_default_blob())

    # 2. Shape unchanged: only assert the frozen version tracks the code (a bare bump left stale).
    if current_hash == frozen_hash:
        assert frozen_version == ENGINE_BLOB_VERSION, (
            f"ENGINE_BLOB_VERSION is {ENGINE_BLOB_VERSION} but the version-lock fixture still "
            f"records {frozen_version}. Regenerate tests/units/stages/fixtures/"
            "default_blob_version.json so the frozen pair tracks the code."
        )
        return

    # 3. Shape changed with a STALE version — the exact miss this lock exists to catch.
    assert ENGINE_BLOB_VERSION != frozen_version, (
        f"The stock ingest blob shape changed but ENGINE_BLOB_VERSION is still {ENGINE_BLOB_VERSION}. "
        "A change that alters what the engine emits for an UNCHANGED PipelineState MUST bump "
        "ENGINE_BLOB_VERSION in shared/libs/pipelines/ingest/stages/normalizer.py, so already-stored "
        "blobs fall out of the fast path and re-heal to the new topology on their next read. Bump it, "
        "then regenerate fixtures/default_blob.json AND fixtures/default_blob_version.json."
    )

    # 4. Shape changed WITH a bump — legitimate; force the fixture refresh that freezes the new pair.
    raise AssertionError(
        "Shape change + ENGINE_BLOB_VERSION bump detected — regenerate "
        "tests/units/stages/fixtures/default_blob_version.json to freeze the new "
        f"(engine_blob_version={ENGINE_BLOB_VERSION}, blob_sha256=…) pair."
    )
