"""Knob B — the create-endpoint's stock-blob preset selector.

``_preset_blob`` picks the light blob for ``preset='light'`` and the full default otherwise; the
create endpoint's ``request.pipeline or CollectionBlobHelpers.preset_blob(request.preset)`` makes an
explicit pipeline win over the preset. Exercised directly (no store, no HTTP) behind the booted app fixture.
"""

from shared_libs.pipelines.ingest import IngestPipeline


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


def test_light_and_default_presets_differ(fastapi_app) -> None:
    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    assert CollectionBlobHelpers.preset_blob("light") != CollectionBlobHelpers.preset_blob(None)


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
