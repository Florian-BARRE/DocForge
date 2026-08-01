"""Knob A — the per-figure enrich loop's max_concurrency is read from the enrich stage config.

``figure_concurrency`` threads blob -> PipelineState (StateReader) -> the assembled per_figure
ForEach, defaulting to 4 when a stored blob omits it (no migration, no break). Raising it
parallelises the paid VLM/OCR calls for image-heavy docs.
"""

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.build.blob import ForEachNodeBlob
from shared_libs.pipelines.ingest.stages import IngestAssembler, StateReader, default_state
from shared_libs.pipelines.validation import GraphValidator


def _per_figure(blob) -> ForEachNodeBlob:
    """The assembled enrich loop node."""
    return next(n for n in blob.nodes if isinstance(n, ForEachNodeBlob) and n.id == "per_figure")


def _enrich_state(**overrides):
    """The stock state with enrich turned on (it ships off) plus any overrides."""
    return default_state().model_copy(update={"enrich_on": True, **overrides})


def test_figure_concurrency_flows_from_state_into_the_per_figure_loop() -> None:
    blob = IngestAssembler.assemble(_enrich_state(figure_concurrency=8))
    assert _per_figure(blob).max_concurrency == 8


def test_default_figure_concurrency_is_four() -> None:
    blob = IngestAssembler.assemble(_enrich_state())
    assert _per_figure(blob).max_concurrency == 4


def test_figure_concurrency_round_trips_through_the_reader() -> None:
    blob = IngestAssembler.assemble(_enrich_state(figure_concurrency=8))
    assert StateReader.read(blob).figure_concurrency == 8


def test_blob_omitting_concurrency_reads_back_as_four() -> None:
    """A stored blob whose ForEach carries the default max_concurrency reads back as 4 — no break."""
    blob = IngestAssembler.assemble(_enrich_state())
    assert StateReader.read(blob).figure_concurrency == 4


def test_raised_concurrency_still_validates_clean() -> None:
    blob = IngestAssembler.assemble(_enrich_state(figure_concurrency=16))
    assert GraphValidator().validate(PipelineBuilder().build(blob)) == []
