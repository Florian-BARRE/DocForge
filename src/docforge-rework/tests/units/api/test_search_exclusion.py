"""P5 search exclusion (facade level). The SearchFacade injects the searchability invariants into
EVERY query, unbypassable from the router, ALL as ``must_not`` exclusions: an ``enabled == false``
match (drops explicitly-disabled chunks' points, while legacy points that predate the payload flag
stay searchable) and a ``must_not`` over the collection's disabled document ids (drops disabled
documents' points), the latter fed by a bounded Postgres lookup. Qdrant + Postgres are fully mocked
— the test proves the FILTER shape, which is what makes Qdrant hide those points at query time."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import SearchFacade
from shared_libs.services.db.facades import search_facade as sf_module
from shared_libs.services.db.qdrant import Match, MatchAny, VectorNames


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


async def test_hybrid_injects_enabled_match_and_disabled_doc_exclusion(monkeypatch) -> None:
    """A disabled document in the collection → an `enabled==false` must_not + a document_id must_not."""
    # 1. Qdrant space exists; capture the hybrid() call and return no hits (skips hydration).
    disabled_id = uuid.uuid4()
    qdrant = MagicMock()
    qdrant.raw.collection_exists = AsyncMock(return_value=True)
    hybrid = AsyncMock(return_value=[])
    monkeypatch.setattr(sf_module.QdrantSearchApi, "hybrid", hybrid)

    # 2. The disabled-doc lookup returns one id (the exclusion set).
    monkeypatch.setattr(
        sf_module.DocumentApi, "list_disabled_ids", AsyncMock(return_value=[disabled_id])
    )
    facade = SearchFacade(_postgres_yielding(MagicMock()), qdrant)

    # 3. Search with a user filter — the system filters must be ADDED, not replace it.
    await facade.hybrid(
        uuid.uuid4(),
        dense={VectorNames.CONTENT_DENSE: [0.1, 0.2]},
        conditions=[Match(field="topic", value="ai")],
    )

    # 4. Conditions carry ONLY the user match (no positive enabled requirement, so legacy points
    #    without the flag survive); both the disabled-chunk flag and the disabled doc are must_not.
    kwargs = hybrid.await_args.kwargs
    assert kwargs["conditions"] == [Match(field="topic", value="ai")]
    assert Match(field="enabled", value=False) not in kwargs["conditions"]
    assert kwargs["exclusions"] == [
        Match(field="enabled", value=False),
        MatchAny(field="document_id", values=[str(disabled_id)]),
    ]


async def test_hybrid_has_no_exclusion_when_no_disabled_docs(monkeypatch) -> None:
    """No disabled documents → conditions stay empty; the enabled==false guard is the only must_not."""
    # 1. Space exists, no hits, and an EMPTY disabled-doc set.
    qdrant = MagicMock()
    qdrant.raw.collection_exists = AsyncMock(return_value=True)
    hybrid = AsyncMock(return_value=[])
    monkeypatch.setattr(sf_module.QdrantSearchApi, "hybrid", hybrid)
    monkeypatch.setattr(
        sf_module.DocumentApi, "list_disabled_ids", AsyncMock(return_value=[])
    )
    facade = SearchFacade(_postgres_yielding(MagicMock()), qdrant)

    # 2. Plain search — no user filters.
    await facade.hybrid(uuid.uuid4(), dense={VectorNames.CONTENT_DENSE: [0.1]})

    # 3. No positive enabled requirement in conditions; the enabled==false guard is the sole must_not.
    kwargs = hybrid.await_args.kwargs
    assert kwargs["conditions"] == []
    assert kwargs["exclusions"] == [Match(field="enabled", value=False)]
