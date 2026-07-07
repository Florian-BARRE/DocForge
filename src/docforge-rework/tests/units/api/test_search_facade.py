"""SearchFacade.hybrid: the un-ingested guard. A collection provisions its Qdrant space lazily at
first indexing, so searching one that was created but never ingested must return [] (empty hits),
NOT raise and become an HTTP 500. Postgres is never touched when the space does not exist yet."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import SearchFacade
from shared_libs.services.db.qdrant import VectorNames


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
