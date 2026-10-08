"""The config-derived vector layout (embed dense/sparse slots) and the gates it drives: the layout read
off the embed config, the store schema (content axes + the all-or-none sparse IDF modifier), the
missing/mismatched vector rule (``needs_reindex``), and the sparse-only search gates (semantic target
→ 422, dense_only search blob → 422, a sparse vector declared for another encoder → rebuild hint).
``from backend...`` deferred until fastapi_app registered app/."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from qdrant_client import models

from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.facades import IndexStateFacade
from shared_libs.services.db.qdrant import DeclaredVectors, QdrantCollectionApi

_SPARSE_ONLY = VectorLayout(dense=False, sparse=True, sparse_idf=True)
_IDF = models.SparseVectorParams(modifier=models.Modifier.IDF)


def _pipeline(config: dict) -> dict:
    """A one-node ingest blob carrying a dense_sparse embedder with the given slots."""
    embed = {"kind": "dense_sparse", "family": "embed", "id": "embed", "config": config}
    return {"kind": "group", "id": "root", "nodes": [embed], "transitions": [], "bindings": {}}


# --------------------------------------------------------------------------- #
# EmbedBlobResolver.layout — from the CONFIG, never the store
# --------------------------------------------------------------------------- #
def test_layout_follows_the_slots() -> None:
    assert EmbedBlobResolver.layout(_pipeline({})) == VectorLayout()
    assert EmbedBlobResolver.layout(_pipeline({"sparse": None})) == VectorLayout(sparse=False)
    sparse_only = _pipeline({"dense": None, "sparse": {"kind": "bm25_local"}})
    assert EmbedBlobResolver.layout(sparse_only) == _SPARSE_ONLY


def test_layout_defaults_without_or_with_a_broken_embedder() -> None:
    assert EmbedBlobResolver.layout({}) == VectorLayout()
    assert EmbedBlobResolver.layout(None) == VectorLayout()
    assert EmbedBlobResolver.layout(_pipeline({"bogus": 1})) == VectorLayout()


# --------------------------------------------------------------------------- #
# DeclaredVectors + missing_vectors — content axes and modifier mismatch
# --------------------------------------------------------------------------- #
def test_declared_vectors_reads_the_idf_subset_and_mismatches() -> None:
    params = SimpleNamespace(
        vectors={"content_dense": object()},
        sparse_vectors={"content_bm25": models.SparseVectorParams(), "meta_x_bm25": _IDF},
    )
    declared = DeclaredVectors.from_params(params)
    assert declared.idf_sparse == {"meta_x_bm25"}
    assert declared.mismatched(VectorLayout()) == {"meta_x_bm25"}
    assert declared.mismatched(_SPARSE_ONLY) == {"content_bm25"}


def test_missing_reports_content_vectors_the_layout_requires() -> None:
    missing = QdrantCollectionApi.missing_vectors(
        [], [], set(), {"content_bm25"}, layout=VectorLayout()
    )
    assert missing == [("content", "content_dense")]


def test_missing_reports_a_mismatched_required_sparse_vector() -> None:
    """IDF meta vectors (0.28–0.30 local BM25) under a bge config are missing → rebuild."""
    missing = QdrantCollectionApi.missing_vectors(
        [],
        ["x"],
        {"content_dense"},
        {"content_bm25", "meta_x_bm25"},
        layout=VectorLayout(),
        mismatched={"meta_x_bm25"},
    )
    assert missing == [("x", "meta_x_bm25")]


def test_missing_skips_fields_of_an_axis_the_embedder_lacks() -> None:
    missing = QdrantCollectionApi.missing_vectors(
        ["sem"], ["lex"], set(), {"content_bm25", "meta_lex_bm25"}, layout=_SPARSE_ONLY
    )
    assert missing == []


async def test_index_state_missing_reads_the_layout_from_the_stored_config(monkeypatch) -> None:
    from shared_libs.services.db.facades import index_state_facade as module  # noqa: PLC0415

    qdrant = MagicMock()
    qdrant.raw.collection_exists = AsyncMock(return_value=True)
    params = SimpleNamespace(
        vectors={}, sparse_vectors={"content_bm25": models.SparseVectorParams()}
    )
    qdrant.raw.get_collection = AsyncMock(
        return_value=SimpleNamespace(config=SimpleNamespace(params=params))
    )
    collection = SimpleNamespace(
        pipeline=_pipeline({"dense": None, "sparse": {"kind": "bm25_local"}})
    )
    monkeypatch.setattr(module.CollectionApi, "get", AsyncMock(return_value=collection))
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    postgres = SimpleNamespace(session=lambda: session)

    missing = await IndexStateFacade(postgres, qdrant).missing_for(uuid.uuid4(), [], [])

    assert missing == [("content", "content_bm25")]  # declared without the IDF bm25_local needs


async def test_ensure_creates_a_sparse_only_idf_store() -> None:
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.get_aliases = AsyncMock(return_value=SimpleNamespace(aliases=[]))
    client.get_collections = AsyncMock(return_value=SimpleNamespace(collections=[]))
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()

    await QdrantCollectionApi.ensure(
        client, "col_x", dense_dim=0, lexical_fields=["nom"], layout=_SPARSE_ONLY
    )

    kwargs = client.create_collection.await_args.kwargs
    assert kwargs["vectors_config"] == {}
    assert {p.modifier for p in kwargs["sparse_vectors_config"].values()} == {models.Modifier.IDF}


# --------------------------------------------------------------------------- #
# Sparse-only search gates
# --------------------------------------------------------------------------- #
def _target(**kwargs):
    from backend.routers.search.models import SearchTargetModel  # noqa: PLC0415

    return SearchTargetModel(**kwargs)


def test_semantic_target_on_a_sparse_only_collection_is_an_error(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    errors = SearchTargetValidator.validate_search_targets(
        [_target(field="content", semantic=True)], [], None, _SPARSE_ONLY
    )
    assert len(errors) == 1 and "no dense provider" in errors[0]
    ok = SearchTargetValidator.validate_search_targets(
        [_target(field="content", lexical=True)], [], None, _SPARSE_ONLY
    )
    assert ok == []


def test_lexical_target_on_a_dense_only_collection_is_an_error(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    errors = SearchTargetValidator.validate_search_targets(
        [_target(field="content", lexical=True)], [], None, VectorLayout(sparse=False)
    )
    assert len(errors) == 1 and "no sparse provider" in errors[0]


def test_a_mismatched_content_sparse_vector_carries_the_rebuild_hint(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    declared = DeclaredVectors(sparse=frozenset({"content_bm25"}))  # declared without IDF
    errors = SearchTargetValidator.validate_search_targets(
        [_target(field="content", lexical=True)], [], declared, _SPARSE_ONLY
    )
    assert len(errors) == 1
    assert "content has no indexed lexical vector" in errors[0] and "rebuild_index" in errors[0]


def test_a_lexical_content_target_needs_the_store_check(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    assert SearchTargetValidator.needs_store_check([_target(field="content", lexical=True)])
    assert not SearchTargetValidator.needs_store_check([_target(field="content", semantic=True)])


def test_dense_only_search_blob_on_a_sparse_only_collection_is_422(fastapi_app) -> None:
    from backend.routers.collections.helpers import CollectionHelpers  # noqa: PLC0415
    from shared_libs.pipelines.search import SearchPipeline  # noqa: PLC0415

    dense_only = SearchPipeline.dense_only_blob().model_dump(mode="json")
    sparse_only = _pipeline({"dense": None, "sparse": {"kind": "bm25_local"}})

    with pytest.raises(HTTPException) as exc:
        CollectionHelpers.validate_search_blob(dense_only, sparse_only)
    assert exc.value.status_code == 422 and "no dense provider" in exc.value.detail
    CollectionHelpers.validate_search_blob(dense_only, _pipeline({}))  # dense present → fine
    hybrid = SearchPipeline.default_blob().model_dump(mode="json")
    CollectionHelpers.validate_search_blob(hybrid, sparse_only)  # hybrid degrades to lexical


def test_detail_needs_reindex_is_stored_or_missing(fastapi_app) -> None:
    from backend.routers.collections.helpers import CollectionHelpers  # noqa: PLC0415

    collection = SimpleNamespace(
        id=uuid.uuid4(),
        name="c",
        supported_formats=["md"],
        tags=[],
        max_file_size_bytes=1,
        job_timeout_seconds=None,
        trace_verbosity="shape",
        needs_reindex=False,
        created_at=None,
        pipeline={},
        search={},
        title_field=None,
        estimate_overrides=None,
    )
    assert CollectionHelpers.to_model(collection, [], ["content_bm25"]).needs_reindex is True
    assert CollectionHelpers.to_model(collection, [], []).needs_reindex is False
