"""Knob B — the light ingestion preset: a fast, local, free retrieval core.

``light_blob()`` is ``IngestAssembler.assemble(light_state())`` with every enrichment stage off
(figure enrich, the contextualize stack, chunk + document metagen). It must enjoy the same
"always builds" guarantee as ``default_blob`` and pass the graph validator with zero issues, while
``default_blob`` stays unchanged.
"""

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import StageViewer, StateReader
from shared_libs.pipelines.validation import GraphValidator

# The nodes the three disabled enrichment stages own — none may appear in the light blob.
_ENRICHMENT_NODE_IDS = {
    "extract",
    "per_figure",
    "apply",  # figure enrich
    "ctx_meta",
    "ctx_breadcrumb",  # contextualize stack
    "meta_chunk_prep",
    "meta_chunk_loop",
    "meta_chunk_apply",  # chunk metagen
    "meta_doc_prep",
    "meta_doc_loop",
    "meta_doc_apply",  # document metagen
}

# render stays on (it is local, free) alongside the mandatory core.
_LIGHT_ENABLED_STAGES = {"intake", "parse", "render", "chunk", "embed", "deliver"}


def test_light_blob_builds_and_validates_clean() -> None:
    issues = GraphValidator().validate(PipelineBuilder().build(IngestPipeline.light_blob()))
    assert issues == [], issues


def test_light_blob_has_no_enrichment_nodes_but_keeps_the_core() -> None:
    node_ids = {n.id for n in IngestPipeline.light_blob().nodes}
    assert node_ids.isdisjoint(_ENRICHMENT_NODE_IDS), node_ids & _ENRICHMENT_NODE_IDS
    for core_id in ("probe", "parse", "chunk", "embed", "bundle"):
        assert core_id in node_ids, core_id


def test_light_blob_enabled_stages_are_the_core_only() -> None:
    catalog = StageViewer.catalog(StateReader.read(IngestPipeline.light_blob()))
    enabled = {stage.key for stage in catalog.stages if stage.enabled}
    assert enabled == _LIGHT_ENABLED_STAGES


def test_default_blob_still_carries_the_enrichment_stages() -> None:
    """The default is untouched — its contextualize stack nodes are still present."""
    node_ids = {n.id for n in IngestPipeline.default_blob().nodes}
    assert {"ctx_meta", "ctx_breadcrumb"} <= node_ids
