"""SearchFacade.hybrid: the un-ingested guard. A collection provisions its Qdrant space lazily at
first indexing, so searching one that was created but never ingested must return [] (empty hits),
NOT raise and become an HTTP 500. Postgres is never touched when the space does not exist yet."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from qdrant_client import models

from shared_libs.services.db.facades import SearchFacade
from shared_libs.services.db.qdrant import VectorNames
from shared_libs.services.db.qdrant.apis import QdrantSearchApi


async def test_hybrid_returns_empty_when_qdrant_collection_missing() -> None:
    """No Qdrant space yet → empty results, and no Postgres hydration attempted."""
    # 1. A qdrant whose collection does not exist, and a postgres that must stay untouched.
    qdrant = MagicMock()
    qdrant.raw.collection_exists = AsyncMock(return_value=False)
    postgres = MagicMock()
    facade = SearchFacade(postgres, qdrant)

    # 2. Searching an un-ingested collection returns no hits.
    hits = await facade.hybrid(uuid.uuid4(), dense={VectorNames.CONTENT_DENSE: [0.1, 0.2]})

    # 3. Empty, with the existence checked and the rich side never opened.
    assert hits == []
    qdrant.raw.collection_exists.assert_awaited_once()
    postgres.session.assert_not_called()


def _fake_client() -> MagicMock:
    """A qdrant client whose query_points records its call and returns no points."""
    client = MagicMock()
    client.query_points = AsyncMock(return_value=SimpleNamespace(points=[]))
    return client


async def test_colbert_query_nests_the_rrf_pool_and_rescores_with_max_sim() -> None:
    """With a ColBERT query, query_points re-scores a NESTED RRF pool via content_colbert."""
    client = _fake_client()
    await QdrantSearchApi.hybrid(
        client,
        "c",
        dense={VectorNames.CONTENT_DENSE: [0.1, 0.2]},
        sparse=None,
        limit=5,
        colbert=[[0.1, 0.2], [0.3, 0.4]],
        rescore_pool_size=42,
    )
    kwargs = client.query_points.await_args.kwargs
    # 1. The OUTER query is the ColBERT multi-vector, re-scoring over the content_colbert space.
    assert kwargs["using"] == VectorNames.CONTENT_COLBERT
    assert kwargs["query"] == [[0.1, 0.2], [0.3, 0.4]]
    assert kwargs["limit"] == 5
    # 2. The prefetch is a SINGLE nested pool: an RRF fusion capped at rescore_pool_size, whose
    #    own children are the dense/sparse branches.
    prefetch = kwargs["prefetch"]
    assert len(prefetch) == 1
    pool = prefetch[0]
    assert pool.limit == 42
    assert isinstance(pool.query, models.FusionQuery)
    assert pool.prefetch[0].using == VectorNames.CONTENT_DENSE


async def test_no_colbert_query_is_the_single_stage_rrf_call() -> None:
    """Without a ColBERT query, the call is the exact single-stage RRF fusion (no nesting)."""
    client = _fake_client()
    await QdrantSearchApi.hybrid(
        client, "c", dense={VectorNames.CONTENT_DENSE: [0.1, 0.2]}, limit=7
    )
    kwargs = client.query_points.await_args.kwargs
    # 1. The top-level query is the RRF fusion itself — no ColBERT re-score, no nested pool.
    assert isinstance(kwargs["query"], models.FusionQuery)
    assert "using" not in kwargs
    assert kwargs["limit"] == 7
    # 2. The prefetch is the flat list of branches (a plain Prefetch, not a nested pool).
    assert kwargs["prefetch"][0].using == VectorNames.CONTENT_DENSE
    assert kwargs["prefetch"][0].prefetch is None
