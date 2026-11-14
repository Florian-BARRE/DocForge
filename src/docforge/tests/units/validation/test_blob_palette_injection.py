"""BlobStructureValidator takes its palettes through an injected source (R-15), no facade import."""

import pytest

from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.pipeline_registry import PipelineRegistry
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import BlobStructureValidator, BlobValidationError


class _RecordingPalettes:
    """A palette source that records the pipeline keys it was asked for."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def allowed_kinds(self, pipeline_key: str) -> dict[str, set[str]]:
        self.asked.append(pipeline_key)
        return PipelineRegistry.allowed_kinds(pipeline_key)


def test_validator_asks_the_injected_palettes_per_pipeline() -> None:
    palettes = _RecordingPalettes()
    validator = BlobStructureValidator(palettes=palettes)

    validator.validate_ingest(IngestPipeline.default_blob().model_dump())
    validator.validate_search(SearchPipeline.default_blob().model_dump())

    assert palettes.asked == ["ingest", "search"]


def test_an_injected_palette_scopes_the_graph() -> None:
    """An empty palette rejects every node: the injected source, not a hard-wired facade, decides."""

    class _Empty:
        def allowed_kinds(self, pipeline_key: str) -> dict[str, set[str]]:
            return {"intake": set()}

    with pytest.raises(BlobValidationError):
        BlobStructureValidator(palettes=_Empty()).validate_ingest(
            IngestPipeline.default_blob().model_dump()
        )


def test_registry_exposes_the_palette_of_each_pipeline_kind() -> None:
    assert PipelineRegistry.allowed_kinds("ingest") == IngestPipeline.allowed_kinds()
    assert PipelineRegistry.allowed_kinds("search") == SearchPipeline.allowed_kinds()
    with pytest.raises(KeyError):
        PipelineRegistry.allowed_kinds("nope")
