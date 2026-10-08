"""A stored embed config that fails validation must never echo its real api_key: not in a log line
(the layout fallback, the query-embedder probe), not in a raised error (the strict layout used to CREATE
a store schema, the meta-vector embedder rebuild). The strict layout fails fast naming the embed node;
the degrading one keeps answering read paths with the default layout."""

# ====== Standard Library Imports ======
from collections.abc import Iterator

# ====== Third-Party Library Imports ======
import pytest
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver, EmbedLayoutError
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.facades.meta_vector_sync_helpers import MetaVectorSyncHelpers

_SECRET = "sk-REALSECRET-tail-9f3a"


def _broken_pipeline() -> dict:
    """An ingest blob whose embed slot names a removed provider kind and carries a real key.

    A slot-level (model) error is what echoes the WHOLE slot dict — key included — in
    ``str(ValidationError)``; an extra-key error would only echo that key's value.
    """
    dense = {"kind": "removed_provider", "base_url": "http://emb/v1", "api_key": _SECRET}
    embed = {
        "id": "embed",
        "kind": "dense_sparse",
        "family": "embed",
        "config": {"dense": dense, "sparse": None},
    }
    return {"kind": "group", "id": "root", "nodes": [embed], "transitions": [], "bindings": {}}


@pytest.fixture
def logs() -> Iterator[list[str]]:
    """Every log record emitted while the test runs, rendered with its message."""
    captured: list[str] = []
    sink = loggerplusplus.add(lambda message: captured.append(str(message)), level="DEBUG")
    yield captured
    loggerplusplus.remove(sink)


def test_degrading_layout_logs_no_secret_and_keeps_the_default(logs: list[str]) -> None:
    layout = EmbedBlobResolver.layout(_broken_pipeline())

    assert layout == VectorLayout()
    assert any("embed node 'embed'" in line for line in logs)
    assert not any(_SECRET in line or "REALSECRET" in line for line in logs)


def test_strict_layout_fails_fast_naming_the_node_without_the_secret() -> None:
    with pytest.raises(EmbedLayoutError) as caught:
        EmbedBlobResolver.layout_or_raise(_broken_pipeline())

    message = str(caught.value)
    assert "embed node 'embed'" in message and "removed_provider" in message
    assert "REALSECRET" not in message
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_strict_layout_without_an_embed_node_is_the_default() -> None:
    assert EmbedBlobResolver.layout_or_raise({"nodes": []}) == VectorLayout()


def test_meta_vector_embedder_rebuild_error_carries_no_secret() -> None:
    node = _broken_pipeline()["nodes"][0]
    with pytest.raises(EmbedLayoutError) as caught:
        MetaVectorSyncHelpers.rebuild_embedder(node)
    assert "REALSECRET" not in str(caught.value)


async def test_query_embedder_probe_logs_no_secret(fastapi_app, logs: list[str]) -> None:
    from backend.libs.search import QueryEmbedderProbe  # noqa: PLC0415
    from shared_libs.pipelines.reachability import ProbeStatus  # noqa: PLC0415

    status = await QueryEmbedderProbe().classify(_broken_pipeline())

    assert status is ProbeStatus.UNREACHABLE
    assert any("Query embedder rebuild failed" in line for line in logs)
    assert not any("REALSECRET" in line for line in logs)
