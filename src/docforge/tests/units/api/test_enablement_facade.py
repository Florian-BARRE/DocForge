"""P5 enablement facade: reversible enable/disable as a flag flip, never a re-embed. A document
toggle is a pure Postgres flag. A chunk toggle sets enabled_override, recomputes the effective state
(override ?? role_default_enabled(role)) and flips the `enabled` scalar on the chunk's EXISTING
Qdrant point via set_payload — the vector is untouched. Enabling a NEVER-embedded chunk fabricates
no point: it comes back reindex_required=True. Postgres + Qdrant are mocked."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import EnablementFacade
from shared_libs.services.db.facades import enablement_facade as ef_module
from shared_libs.services.db.facades.helpers import DatabaseHelpers


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _chunk(*, is_indexed: bool, role: str = "body") -> SimpleNamespace:
    """A mutable stand-in for a Chunk row (only the fields the facade touches)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        role=role,
        is_indexed=is_indexed,
        enabled_override=None,
    )


async def test_set_document_enabled_flips_the_flag(monkeypatch) -> None:
    """A document toggle is a single Postgres flip; existence is echoed back for the 404 guard."""
    set_enabled = AsyncMock(return_value=True)
    monkeypatch.setattr(ef_module.DocumentApi, "set_enabled", set_enabled)
    facade = EnablementFacade(_postgres_yielding(MagicMock()), MagicMock())

    existed = await facade.set_document_enabled(uuid.uuid4(), False)

    assert existed is True
    assert set_enabled.await_args.args[2] is False  # (session, document_id, enabled)


async def test_toggle_embedded_chunk_flips_payload(monkeypatch) -> None:
    """An indexed chunk: override written + its point's `enabled` set to the effective value."""
    # 1. One embedded body chunk; its document resolves the Qdrant collection.
    chunk = _chunk(is_indexed=True)
    collection_id = uuid.uuid4()
    document = SimpleNamespace(id=chunk.document_id, collection_id=collection_id)
    monkeypatch.setattr(ef_module.ChunkApi, "get_by_ids", AsyncMock(return_value=[chunk]))
    monkeypatch.setattr(ef_module.DocumentApi, "get_by_ids", AsyncMock(return_value=[document]))
    set_payload = AsyncMock()
    monkeypatch.setattr(ef_module.QdrantIndexApi, "set_payload", set_payload)
    facade = EnablementFacade(_postgres_yielding(MagicMock()), MagicMock())

    # 2. Disable the chunk.
    outcomes = await facade.set_chunks_enabled([chunk.id], False)

    # 3. Override persisted, effective recomputed, payload flipped on the right collection.
    assert chunk.enabled_override is False
    assert outcomes[0].enabled is False
    assert outcomes[0].reindex_required is False
    name = DatabaseHelpers.qdrant_collection_name(collection_id)
    set_payload.assert_awaited_once_with(
        facade._qdrant.raw, name, {str(chunk.id): {"enabled": False}}
    )


async def test_enable_never_embedded_chunk_requires_reindex(monkeypatch) -> None:
    """Enabling a chunk with NO Qdrant point returns reindex_required and fabricates no point."""
    # 1. A non-indexed chunk (e.g. a header/footer that embed skipped).
    chunk = _chunk(is_indexed=False, role="header_footer")
    document = SimpleNamespace(id=chunk.document_id, collection_id=uuid.uuid4())
    monkeypatch.setattr(ef_module.ChunkApi, "get_by_ids", AsyncMock(return_value=[chunk]))
    monkeypatch.setattr(ef_module.DocumentApi, "get_by_ids", AsyncMock(return_value=[document]))
    set_payload = AsyncMock()
    monkeypatch.setattr(ef_module.QdrantIndexApi, "set_payload", set_payload)
    facade = EnablementFacade(_postgres_yielding(MagicMock()), MagicMock())

    # 2. Enable it.
    outcomes = await facade.set_chunks_enabled([chunk.id], True)

    # 3. The override is recorded, but NO point was flipped and the caller is told a reindex is due.
    assert chunk.enabled_override is True
    assert outcomes[0].enabled is True
    assert outcomes[0].reindex_required is True
    set_payload.assert_not_awaited()


async def test_unknown_chunk_ids_yield_no_outcomes(monkeypatch) -> None:
    """An unknown id resolves to no chunk — an empty result the router maps to a 404."""
    monkeypatch.setattr(ef_module.ChunkApi, "get_by_ids", AsyncMock(return_value=[]))
    facade = EnablementFacade(_postgres_yielding(MagicMock()), MagicMock())

    outcomes = await facade.set_chunks_enabled([uuid.uuid4()], True)

    assert outcomes == []
