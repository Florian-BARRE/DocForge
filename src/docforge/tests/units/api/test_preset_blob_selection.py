"""Knob B — the create-endpoint's stock-blob preset selectors (ingestion + search).

``CollectionBlobHelpers.preset_blob`` delegates to ``IngestPipeline.preset_blob`` (the curated stock
topologies have ONE definition); ``search_preset_blob`` delegates to ``SearchPipeline.preset_blob``
but collapses the default to the ``{}`` sentinel. The create endpoint's
``request.pipeline or CollectionBlobHelpers.preset_blob(request.preset)`` makes an explicit pipeline
win over the preset. Exercised directly (no store, no HTTP) behind the booted app fixture.
"""

from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.search import SearchPipeline


def test_preset_light_selects_the_light_blob(fastapi_app) -> None:
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    assert CollectionBlobHelpers.preset_blob("light") == IngestPipeline.light_blob().model_dump(
        mode="json"
    )


def test_preset_standard_and_none_select_the_default_blob(fastapi_app) -> None:
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    default = IngestPipeline.default_blob().model_dump(mode="json")
    assert CollectionBlobHelpers.preset_blob("standard") == default
    assert CollectionBlobHelpers.preset_blob(None) == default


def test_preset_ocr_scan_and_high_precision_select_their_blobs(fastapi_app) -> None:
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    assert CollectionBlobHelpers.preset_blob(
        "ocr_scan"
    ) == IngestPipeline.ocr_scan_blob().model_dump(mode="json")
    assert CollectionBlobHelpers.preset_blob(
        "high_precision"
    ) == IngestPipeline.high_precision_blob().model_dump(mode="json")


def test_every_ingest_preset_is_distinct(fastapi_app) -> None:
    """The four offered ingestion presets must each produce a DIFFERENT stock blob."""
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    names = [preset.name for preset in IngestPipeline.presets()]
    blobs = [CollectionBlobHelpers.preset_blob(name) for name in names]
    # Every pair differs (JSON-ready dicts are comparable).
    for i, left in enumerate(blobs):
        for right in blobs[i + 1 :]:
            assert left != right


def test_unknown_ingest_preset_falls_back_to_default(fastapi_app) -> None:
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    assert CollectionBlobHelpers.preset_blob("does_not_exist") == CollectionBlobHelpers.preset_blob(
        None
    )


def test_search_preset_default_and_none_collapse_to_the_empty_sentinel(fastapi_app) -> None:
    """The default search preset (and None) store {} — the stock-default sentinel, no redundant graph."""
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    assert CollectionBlobHelpers.search_preset_blob(None) == {}
    assert CollectionBlobHelpers.search_preset_blob("hybrid") == {}


def test_search_preset_non_default_selects_its_blob(fastapi_app) -> None:
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    assert CollectionBlobHelpers.search_preset_blob(
        "hybrid_rerank"
    ) == SearchPipeline.rerank_blob().model_dump(mode="json")
    assert CollectionBlobHelpers.search_preset_blob(
        "dense_only"
    ) == SearchPipeline.dense_only_blob().model_dump(mode="json")


def test_explicit_pipeline_wins_over_preset(fastapi_app) -> None:
    """Mirror the endpoint's selection expression: an explicit graph bypasses the preset entirely."""
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415
    from backend.routers.collections.models import CreateCollectionRequest  # noqa: PLC0415

    explicit = {"node_type": "group", "id": "custom", "nodes": []}
    request = CreateCollectionRequest(
        name="x",
        supported_formats=["pdf"],
        max_file_size_bytes=1,
        pipeline=explicit,
        preset="light",
    )
    assert (request.pipeline or CollectionBlobHelpers.preset_blob(request.preset)) == explicit
