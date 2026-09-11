"""Business presets — every curated preset builds a valid blob, and presets() self-describes cleanly.

A preset is a curated, validation-passing stock blob (a starting point, NOT a new engine): each must
build into a graph the ``GraphValidator`` accepts with zero issues, exactly like the stock default.
Both pipeline facades (ingest + search) expose the same ``presets()`` / ``preset_blob()`` contract;
this locks that contract for both, plus the dense-only normalize knob that backs the search preset.
"""

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import GraphValidator

_FACADES = {"ingest": IngestPipeline, "search": SearchPipeline}


@pytest.mark.parametrize("facade", _FACADES.values(), ids=list(_FACADES))
def test_every_preset_builds_and_validates_clean(facade) -> None:
    """Each offered preset assembles a blob the validator accepts with zero issues."""
    validator = GraphValidator()
    builder = PipelineBuilder()
    presets = facade.presets()
    assert presets, "a facade must offer at least one preset"
    for preset in presets:
        blob = facade.preset_blob(preset.name)
        issues = validator.validate(builder.build(blob))
        assert issues == [], f"{preset.name}: {issues}"


@pytest.mark.parametrize("facade", _FACADES.values(), ids=list(_FACADES))
def test_presets_metadata_is_well_formed(facade) -> None:
    """Exactly one default, unique non-empty names, and a label + rationale on each."""
    presets = facade.presets()
    names = [p.name for p in presets]
    assert len(names) == len(set(names)), names
    assert sum(1 for p in presets if p.is_default) == 1, "exactly one default preset"
    for preset in presets:
        assert preset.name and preset.label and preset.description


@pytest.mark.parametrize("facade", _FACADES.values(), ids=list(_FACADES))
def test_default_preset_blob_equals_default_blob(facade) -> None:
    """The default preset resolves to the facade's canonical default_blob (no drift)."""
    default_name = next(p.name for p in facade.presets() if p.is_default)
    assert facade.preset_blob(default_name) == facade.default_blob()
    # An omitted / unknown name also falls back to the default blob.
    assert facade.preset_blob(None) == facade.default_blob()


def test_ocr_scan_preset_uses_a_local_ocr_chain_no_provider_hosted() -> None:
    """The ocr_scan preset enriches via a LOCAL rapidocr chain — no SET_ME provider-hosted step."""
    blob = IngestPipeline.ocr_scan_blob().model_dump(mode="json")
    dumped = repr(blob)
    assert "rapidocr" in dumped
    # No placeholder secret: the preset must stay preflight-clean / free out of the box.
    assert "SET_ME" not in dumped


def test_dense_only_preset_narrows_normalize_to_semantic() -> None:
    """The dense_only search preset sets normalize.content_modalities='semantic'; hybrid leaves default."""
    dense = SearchPipeline.dense_only_blob()
    normalize = next(n for n in dense.nodes if n.id == "normalize")
    assert normalize.config.get("content_modalities") == "semantic"
    # The default (hybrid) blob does NOT carry the override.
    hybrid_norm = next(n for n in SearchPipeline.default_blob().nodes if n.id == "normalize")
    assert "content_modalities" not in (hybrid_norm.config or {})
