# ====== Code Summary ======
# Characterization of every place that hashes a PIPELINE BLOB today (safety net for a future single
# BlobHasher). One fixed blob dict goes through each form and the exact digest is the golden:
#   A. app documents router ``_pipeline_version`` — sha256 of json(sort_keys, default=str), cut to 16 hex
#   B. worker ``jobs/core.py``  ``config_hash`` — same expression, the full 64 hex
#   C. worker ``jobs/replay.py`` ``config_hash`` — same expression again (the replay path)
#   D. worker ``PipelineRunner.__blob_hash`` — compact separators, sort_keys, default=str
#   E. worker ``CacheKeyBuilder.config_fingerprint`` — the same compact form, for a stage config subtree
# A/B/C agree (A is B's 16-hex prefix); D/E agree; the two families DIFFER (separators). A refactor must
# keep every digest — or deliberately change one and say so. The forms are lifted from the source files
# (see HashFormExtractor): the app and worker packages cannot be imported in one process.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Callable

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from .support.hash_form_extractor import HashFormExtractor

# A small blob exercising nested dicts, a list, a non-ASCII string and a non-JSON value (UUID, which
# every form stringifies through ``default=str``).
BLOB: dict = {
    "nodes": [
        {
            "id": "n1",
            "family": "chunker",
            "kind": "recursive",
            "config": {"size": 512, "overlap": 64},
        },
        {
            "id": "n2",
            "family": "embed",
            "kind": "bge_m3",
            "config": {"model": "é", "id": uuid.UUID("11111111-1111-1111-1111-111111111111")},
        },
    ],
    "edges": [["n1", "n2"]],
}

#: The same blob with the top-level keys and each node's keys inserted in reverse order.
REVERSED_BLOB: dict = {
    "edges": BLOB["edges"],
    "nodes": [{key: node[key] for key in reversed(list(node))} for node in BLOB["nodes"]],
}

DIGEST_DEFAULT_SEPARATORS = "a0d55c34f0131cd069aff60697aae366b57f4377f74cbf673b71941715c559a9"
DIGEST_COMPACT_SEPARATORS = "14377d44a0fad08cef7304180f576bf9c9ddb0e6ffb2335fc36d723d0c0e2398"

FORMS: dict[str, tuple[Callable[[dict], str], str]] = {
    "router._pipeline_version": (
        HashFormExtractor.function("app/backend/routers/documents/router.py", "_pipeline_version"),
        DIGEST_DEFAULT_SEPARATORS[:16],
    ),
    "jobs/core.config_hash": (
        lambda blob: HashFormExtractor.assigned_expression(
            "worker/backend/libs/jobs/core.py", "config_hash", {"blob": blob}
        ),
        DIGEST_DEFAULT_SEPARATORS,
    ),
    "jobs/replay.config_hash": (
        lambda blob: HashFormExtractor.assigned_expression(
            "worker/backend/libs/jobs/replay.py", "config_hash", {"blob": blob}
        ),
        DIGEST_DEFAULT_SEPARATORS,
    ),
    "runner.PipelineRunner.__blob_hash": (
        HashFormExtractor.function(
            "worker/backend/libs/runner/core.py", "PipelineRunner.__blob_hash"
        ),
        DIGEST_COMPACT_SEPARATORS,
    ),
    "cache.CacheKeyBuilder.config_fingerprint": (
        HashFormExtractor.function(
            "worker/backend/libs/runner/cache/keys.py", "CacheKeyBuilder.config_fingerprint"
        ),
        DIGEST_COMPACT_SEPARATORS,
    ),
}


@pytest.mark.parametrize("form", FORMS)
def test_form_produces_its_golden_digest(form: str) -> None:
    """Each hashing form returns the exact digest recorded for the fixed blob."""
    hasher, expected = FORMS[form]
    assert hasher(BLOB) == expected


@pytest.mark.parametrize("form", FORMS)
def test_form_ignores_dict_key_order(form: str) -> None:
    """Every form sorts keys: the same blob built in another order hashes identically."""
    hasher, expected = FORMS[form]
    assert hasher(REVERSED_BLOB) == expected


@pytest.mark.parametrize("form", FORMS)
def test_form_changes_with_the_blob_content(form: str) -> None:
    """A changed config value changes the digest (the dedup / cache key really tracks the blob)."""
    hasher, expected = FORMS[form]
    changed = {**BLOB, "edges": [["n1", "n3"]]}
    assert hasher(changed) != expected


def test_router_version_is_the_sixteen_hex_prefix_of_the_worker_config_hash() -> None:
    """The document's dedup version and the chunks' config_hash are the same digest, cut vs full."""
    router, _ = FORMS["router._pipeline_version"]
    worker, _ = FORMS["jobs/core.config_hash"]
    assert len(router(BLOB)) == 16
    assert worker(BLOB).startswith(router(BLOB))


def test_ingest_and_replay_config_hash_agree() -> None:
    """The ingest and the replay path stamp the same config_hash for the same blob."""
    core, _ = FORMS["jobs/core.config_hash"]
    replay, _ = FORMS["jobs/replay.config_hash"]
    assert core(BLOB) == replay(BLOB)


def test_runner_cache_axis_equals_the_stage_config_fingerprint() -> None:
    """The runner's blob hash and the cache key's config fingerprint share the compact form."""
    runner, _ = FORMS["runner.PipelineRunner.__blob_hash"]
    fingerprint, _ = FORMS["cache.CacheKeyBuilder.config_fingerprint"]
    assert runner(BLOB) == fingerprint(BLOB)


def test_the_two_hash_families_are_distinct() -> None:
    """The config_hash family and the runner/cache family hash the same blob to different digests."""
    assert DIGEST_DEFAULT_SEPARATORS != DIGEST_COMPACT_SEPARATORS
    assert FORMS["jobs/core.config_hash"][0](BLOB) != FORMS["runner.PipelineRunner.__blob_hash"][0](
        BLOB
    )
