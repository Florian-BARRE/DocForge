# ====== Code Summary ======
# EstimateOverrideMerger — folding a collection's PARTIAL estimate overrides over the estimator's
# global defaults. Locks the per-field precedence documented in merger.py: an absent subtree falls
# through untouched, a provided rate MAP overlays only its own keys (never a wholesale replace), and
# the collection's ACTUAL chunker config always wins on top for chunk sizing, even when an override
# also names it. `EstimateOverrideMerger` lives under `backend.libs.estimate` (the app namespace), so
# this module bootstraps `app/` onto sys.path itself rather than depending on the `tests/units/api/`
# fixture — see the ``_app_on_path`` fixture below.

# ====== Standard Library Imports ======
import pathlib
import sys

# ====== Third-Party Library Imports ======
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "app"


@pytest.fixture(scope="module", autouse=True)
def _app_on_path():
    """Register app/ on sys.path (idempotent) so ``backend.libs.estimate.*`` resolves."""
    app_dir_str = str(APP_DIR)
    if app_dir_str not in sys.path:
        sys.path.insert(0, app_dir_str)
    from config import RUNTIME_CONFIG  # noqa: F401,PLC0415 — side-effect import (path registration)


def _merger():
    from backend.libs.estimate.merger import EstimateOverrideMerger  # noqa: PLC0415

    return EstimateOverrideMerger


def _overrides_cls():
    from backend.libs.estimate.overrides import EstimateOverrides  # noqa: PLC0415

    return EstimateOverrides


# ── merged_rates ────────────────────────────────────────────────────────────────────────────────


def test_merged_rates_with_no_overrides_returns_the_canonical_defaults():
    from shared_libs.pipelines.ingest.estimate import RateTable  # noqa: PLC0415

    merger, defaults = _merger(), RateTable.default()
    merged = merger.merged_rates(None)

    assert merged.chat == defaults.chat
    assert merged.embed == defaults.embed
    assert merged.ocr_per_page == defaults.ocr_per_page


def test_merged_rates_with_an_empty_override_object_returns_the_defaults():
    from shared_libs.pipelines.ingest.estimate import RateTable  # noqa: PLC0415

    merger, defaults = _merger(), RateTable.default()
    merged = merger.merged_rates(_overrides_cls()())  # rates=None inside a present overrides object

    assert merged.chat == defaults.chat
    assert merged.embed == defaults.embed


def test_merged_rates_model_override_adds_a_new_entry_without_dropping_defaults():
    from shared_libs.pipelines.ingest.estimate import RateTable  # noqa: PLC0415

    defaults = RateTable.default()
    override = _overrides_cls()(rates={"models": {"custom-model": {"input": 1.0, "output": 2.0}}})

    merged = _merger().merged_rates(override)

    assert merged.chat["custom-model"] == (1.0, 2.0)
    # Every canonical default model survives the merge untouched.
    for model, rate in defaults.chat.items():
        assert merged.chat[model] == rate


def test_merged_rates_model_override_replaces_an_existing_key_only():
    from shared_libs.pipelines.ingest.estimate import RateTable  # noqa: PLC0415

    defaults = RateTable.default()
    known_model = next(iter(defaults.chat))
    override = _overrides_cls()(rates={"models": {known_model: {"input": 99.0, "output": 100.0}}})

    merged = _merger().merged_rates(override)

    assert merged.chat[known_model] == (99.0, 100.0)
    assert len(merged.chat) == len(defaults.chat)  # no key added, none dropped


def test_merged_rates_embed_and_ocr_overrides_are_independent_overlays():
    from shared_libs.pipelines.ingest.estimate import RateTable  # noqa: PLC0415

    defaults = RateTable.default()
    override = _overrides_cls()(rates={"embed": {"custom-embed": 0.5}, "ocr": {"custom-ocr": 2.0}})

    merged = _merger().merged_rates(override)

    assert merged.embed["custom-embed"] == 0.5
    assert merged.ocr_per_page["custom-ocr"] == 2.0
    # The chat map is entirely untouched when the override names no models.
    assert merged.chat == defaults.chat
    for model, rate in defaults.embed.items():
        assert merged.embed[model] == rate


# ── merged_assumptions ──────────────────────────────────────────────────────────────────────────


def test_merged_assumptions_with_no_overrides_uses_chunker_config_for_sizing():
    merged = _merger().merged_assumptions(None, {"target_tokens": 800, "overlap_tokens": 200})

    assert merged.target_chunk_tokens == 800
    assert merged.chunk_overlap_ratio == 200 / 800
    # A non-sizing field falls through to the estimator's own default.
    assert merged.tokens_per_page == 500.0


def test_merged_assumptions_falls_back_to_max_tokens_when_target_tokens_is_absent():
    merged = _merger().merged_assumptions(None, {"max_tokens": 1000})

    assert merged.target_chunk_tokens == 1000
    assert merged.chunk_overlap_ratio == 0.0  # no overlap key -> 0


def test_merged_assumptions_empty_chunker_config_falls_back_to_the_base_default():
    merged = _merger().merged_assumptions(None, {})

    assert merged.target_chunk_tokens == 512  # EstimateAssumptions' own default
    assert merged.chunk_overlap_ratio == 0.0


def test_merged_assumptions_applies_only_the_provided_override_fields():
    override = _overrides_cls()(assumptions={"tokens_per_page": 700.0})

    merged = _merger().merged_assumptions(override, {})

    assert merged.tokens_per_page == 700.0
    # Every field the override didn't name keeps the estimator's own default.
    assert merged.bytes_per_token == 4.0


def test_merged_assumptions_overlap_override_is_consumed_when_chunker_is_silent():
    """When the chunker config declares NO overlap_tokens, chunk_overlap_ratio falls back to the
    merged base — so a caller's chunk_overlap_ratio override is honoured (it was previously dead,
    hard-forced to 0). target_tokens present keeps the chunker authoritative for sizing."""
    override = _overrides_cls()(assumptions={"chunk_overlap_ratio": 0.25})

    merged = _merger().merged_assumptions(override, {"target_tokens": 800})

    assert merged.target_chunk_tokens == 800
    assert merged.chunk_overlap_ratio == 0.25


def test_merged_assumptions_explicit_zero_overlap_tokens_keeps_the_chunker_authoritative():
    """An EXPLICIT overlap_tokens=0 means the chunker declares 'no overlap' and wins — it must NOT
    fall back to a caller's override (the explicit-vs-absent distinction)."""
    override = _overrides_cls()(assumptions={"chunk_overlap_ratio": 0.9})

    merged = _merger().merged_assumptions(override, {"target_tokens": 1024, "overlap_tokens": 0})

    assert merged.chunk_overlap_ratio == 0.0


def test_merged_assumptions_chunker_config_wins_over_an_assumption_override_for_sizing():
    """The pipeline's ACTUAL chunker config is authoritative for chunk sizing even when the
    override also names target_chunk_tokens/chunk_overlap_ratio (the documented precedence)."""
    override = _overrides_cls()(
        assumptions={"target_chunk_tokens": 256, "chunk_overlap_ratio": 0.9}
    )

    merged = _merger().merged_assumptions(override, {"target_tokens": 1024, "overlap_tokens": 0})

    assert merged.target_chunk_tokens == 1024
    assert merged.chunk_overlap_ratio == 0.0
