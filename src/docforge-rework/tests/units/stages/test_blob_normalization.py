"""BlobNormalizer — the losslessness proof, the stale-blob auto-heal, and the clear-error path.

The durable source of truth is the stage-level PipelineState, not the expanded blob (which embeds
engine-structural wiring that shifts as the engine evolves). Normalization round-trips a stored blob
through that truth (read -> PipelineState -> assemble) to the current-engine topology. The core
contract this file locks:

1. LOSSLESSNESS — ``assemble(read(blob)) == blob`` for the default AND every representative
   user-customisable shape (swapped provider, multi-step chain with score_below, disabled optional
   stages, edited node config, each figure-class branch, the externalised llm contextualize method).
   If any shape were lossy, the assert would fail here rather than silently altering a user's
   pipeline at run time.
2. STALE AUTO-HEAL — a blob missing engine-structural wiring is re-emitted whole.
3. VERSION STAMP — a stamped-current blob fast-paths (round-trip skipped); the stamp is idempotent.
4. CLEAR ERROR — an unmigratable blob raises BlobNormalizationError, never a silent alteration.
"""

import copy

import pytest

from shared_libs.pipelines.ingest.stages import (
    BlobNormalizationError,
    BlobNormalizer,
    IngestAssembler,
    default_state,
)
from shared_libs.pipelines.ingest.stages.models import ChainSpec, ChainStep, StackMethod


def _assert_lossless(state) -> None:
    """Assemble a state, then assert normalization re-emits its blob byte-for-byte."""
    blob = IngestAssembler.assemble(state).model_dump(mode="json")
    assert BlobNormalizer.normalize(blob) == blob, "round-trip is NOT lossless for this shape"


# --------------------------------------------------------------------------- losslessness

def test_default_blob_round_trips_identically() -> None:
    _assert_lossless(default_state())


def test_swapped_provider_round_trips() -> None:
    state = default_state()
    state.chunker_kind = "fixed_size"
    state.embed_chain = ChainSpec(
        family="embed",
        steps=[ChainStep(kind="openai_compatible", config={"base_url": "http://x/v1", "model": "m"})],
    )
    _assert_lossless(state)


def test_multistep_chain_with_score_below_round_trips() -> None:
    state = default_state()
    state.parse_chain = ChainSpec(
        family="parser",
        steps=[ChainStep(kind="docling", score_below=0.5), ChainStep(kind="docling", config={"foo": 1})],
    )
    _assert_lossless(state)


def test_disabled_optional_stages_round_trip() -> None:
    state = default_state()
    state.enrich_on = False
    state.render_on = False
    state.metadoc_on = False
    state.metachunk_on = False
    state.embed_on = False
    _assert_lossless(state)


def test_edited_node_config_round_trips() -> None:
    state = default_state()
    state.chunker_config = {"max_tokens": 512}
    state.classify_config = {"base_url": "http://vlm:8000/v1", "model": "qwen2.5-vl", "threshold": 0.7}
    _assert_lossless(state)


def test_each_figure_class_branch_round_trips() -> None:
    """A swapped enrich chain (reordered OCR with a score threshold) on a figure branch."""
    state = default_state()
    state.chains = dict(state.chains)
    state.chains["scanned_text_ocr"] = ChainSpec(
        family="ocr",
        steps=[ChainStep(kind="mistral", config={"api_key": "K"}, score_below=0.6),
               ChainStep(kind="rapidocr", config={})],
    )
    _assert_lossless(state)


def test_reordered_stack_round_trips() -> None:
    state = default_state()
    state.stack = [StackMethod(kind="breadcrumb", config={}), StackMethod(kind="doc_meta", config={})]
    _assert_lossless(state)


def test_llm_contextualize_method_round_trips() -> None:
    """The externalised prep -> ForEach(llm chain) -> apply subgraph, single-step and multi-step."""
    state = default_state()
    state.stack = [
        StackMethod(kind="doc_meta", config={}),
        StackMethod(
            kind="llm", config={"document_scope": "section"},
            chain=ChainSpec(family="llm", steps=[
                ChainStep(kind="openai_compatible", config={"base_url": "http://llm:8000/v1", "model": "m"})]),
        ),
        StackMethod(kind="breadcrumb", config={}),
    ]
    _assert_lossless(state)

    state.stack = [
        StackMethod(
            kind="llm", config={"document_scope": "document"},
            chain=ChainSpec(family="llm", steps=[
                ChainStep(kind="openai_compatible", config={"base_url": "http://a/v1", "model": "a"}),
                ChainStep(kind="openai_compatible", config={"base_url": "http://b/v1", "model": "b"})]),
        ),
    ]
    _assert_lossless(state)


def test_multistep_metagen_chain_round_trips() -> None:
    state = default_state()
    state.metachunk_chain = ChainSpec(
        family="structgen",
        steps=[ChainStep(kind="openai_compatible", config={"base_url": "http://a/v1"}),
               ChainStep(kind="openai_compatible", config={"base_url": "http://b/v1"})],
    )
    _assert_lossless(state)


# --------------------------------------------------------------------------- version stamp

def test_stamp_is_current_and_normalize_fast_paths() -> None:
    blob = IngestAssembler.assemble(default_state()).model_dump(mode="json")
    stored = BlobNormalizer.stamp(blob)

    assert stored[BlobNormalizer.STAMP_KEY] == 1
    # A stamped-current blob normalizes to the stripped-but-identical topology (round-trip skipped).
    assert BlobNormalizer.normalize(stored) == blob
    # Stamping is idempotent — re-storing a canonical blob is a no-op.
    assert BlobNormalizer.stamp(stored) == stored


# --------------------------------------------------------------------------- stale auto-heal

def test_stale_blob_missing_structural_wiring_is_healed_whole() -> None:
    """Simulate an engine change that ADDED a node: drop a leaf from a stored blob; normalization
    re-emits the full current topology (the exact fix for the fundamental error)."""
    blob = IngestAssembler.assemble(default_state()).model_dump(mode="json")
    stale = copy.deepcopy(blob)
    stale["nodes"] = [node for node in stale["nodes"] if node.get("id") != "bundle"]

    healed = BlobNormalizer.normalize(stale)

    assert any(node.get("id") == "bundle" for node in healed["nodes"])
    assert healed == blob


# --------------------------------------------------------------------------- clear error

def test_unmigratable_blob_raises_clear_error() -> None:
    with pytest.raises(BlobNormalizationError, match="re-save it from the pipeline default"):
        BlobNormalizer.normalize({"garbage": True, "nodes": "not-a-list"})


def test_blob_with_unregistered_kind_raises_clear_error_not_silent_drop() -> None:
    """A STRUCTURALLY-valid blob referencing a (family, kind) the engine no longer knows must fail
    loud + named — the reader would otherwise silently drop the unknown node and heal to a DIFFERENT
    pipeline. This is the silent-alteration class this layer exists to eliminate."""
    blob = {
        "id": "root",
        "nodes": [{"id": "gone", "family": "metagen", "kind": "chunk", "config": {}}],
        "transitions": [],
        "bindings": {},
    }
    with pytest.raises(BlobNormalizationError, match="chunk"):
        BlobNormalizer.normalize(blob)
