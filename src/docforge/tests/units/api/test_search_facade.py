"""SearchFacade.hybrid_ids: the un-ingested guard. A collection provisions its Qdrant space lazily at
first indexing, so searching one that was created but never ingested must return [] (empty pairs),
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
    hits = await facade.hybrid_ids(uuid.uuid4(), dense={VectorNames.CONTENT_DENSE: [0.1, 0.2]})

    # 3. Empty, with the existence checked and the rich side never opened.
    assert hits == []
    qdrant.raw.collection_exists.assert_awaited_once()
    postgres.session.assert_not_called()


def _fake_client() -> MagicMock:
    """A qdrant client whose query_points records its call and returns no points."""
    client = MagicMock()
    client.query_points = AsyncMock(return_value=SimpleNamespace(points=[]))
    return client


async def test_hybrid_query_is_the_single_stage_rrf_call() -> None:
    """The call is the single-stage RRF fusion (a flat list of branches, no nesting)."""
    client = _fake_client()
    await QdrantSearchApi.hybrid(
        client, "c", dense={VectorNames.CONTENT_DENSE: [0.1, 0.2]}, limit=7
    )
    kwargs = client.query_points.await_args.kwargs
    # 1. The top-level query is the RRF fusion itself — no nested pool.
    assert isinstance(kwargs["query"], models.FusionQuery)
    assert "using" not in kwargs
    assert kwargs["limit"] == 7
    # 2. The prefetch is the flat list of branches (a plain Prefetch, not a nested pool).
    assert kwargs["prefetch"][0].using == VectorNames.CONTENT_DENSE
    assert kwargs["prefetch"][0].prefetch is None
