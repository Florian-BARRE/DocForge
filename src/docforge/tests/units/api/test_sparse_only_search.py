"""A sparse-only collection (dense slot off, ``bm25_local`` sparse) searches end to end with mocked
stores: the default search graph rebuilds the real ``dense_sparse`` embedder from the contract, encodes
NO dense vector, the real read port queries ``content_bm25`` alone (unfused) and the response's score
kind is ``raw_sparse``. ``from backend...`` deferred until fastapi_app registered app/."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.search import COLLECTION_READ_CAPABILITY, SearchPipeline
from shared_libs.public_models.search import QueryFilters, RawQuery, SearchContract

_SPARSE_ONLY = {"dense": None, "sparse": {"kind": "bm25_local"}}


def _database(chunk_id: uuid.UUID) -> SimpleNamespace:
    document_id = uuid.uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        text="Passation des marchés.",
        chunk_index=0,
        token_count=4,
        heading_path=[],
    )
    return SimpleNamespace(
        search=SimpleNamespace(hybrid_ids=AsyncMock(return_value=[(str(chunk_id), 2.7)])),
        documents=SimpleNamespace(
            get_chunks_by_ids=AsyncMock(return_value=[chunk]),
            get_by_ids=AsyncMock(
                return_value=[SimpleNamespace(id=document_id, filename="a.md", title="A")]
            ),
            get_filterable_metadata_for_documents=AsyncMock(return_value={document_id: {}}),
            get_block_locations_for_chunks=AsyncMock(return_value={}),
        ),
    )


def test_sparse_only_collection_searches_content_bm25_raw(fastapi_app) -> None:
    from backend.libs.search import CollectionReadPortImpl
    from backend.libs.search.probe import AXES_SPARSE_ONLY
    from backend.libs.search.score_kind import ScoreKindClassifier

    chunk_id = uuid.uuid4()
    database = _database(chunk_id)
    port = CollectionReadPortImpl(database, uuid.uuid4())
    group = PipelineBuilder().build(SearchPipeline.default_blob())
    for child in group.children:
        if isinstance(child, ActionNode):
            child.bind({COLLECTION_READ_CAPABILITY: port})
    run_input = {
        "query": RawQuery(text="passation des marchés", top_k=3, flags={}),
        "filters": QueryFilters(filters={}),
        "contract": SearchContract(
            collection_id="c", embed_kind="dense_sparse", embed_config=_SPARSE_ONLY
        ),
    }

    output, record = asyncio.run(FlowEngine().execute(group, run_input))

    assert record.status.value == "success", record
    assert [hit.chunk_id for hit in output.result.hits] == [str(chunk_id)]
    call = database.search.hybrid_ids.await_args.kwargs
    assert not call["dense"]  # no dense axis queried
    assert set(call["sparse"]) == {"content_bm25"}
    assert call["sparse"]["content_bm25"].indices  # the bm25_local query terms
    assert port.probe.raw_axis() == AXES_SPARSE_ONLY
    assert ScoreKindClassifier.raw_kind(port.probe.raw_axis()) == "raw_sparse"
