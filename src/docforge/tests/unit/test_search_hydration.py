# ====== Code Summary ======
# Unit tests for HybridSearchHelpers.hydrate():
# flat chunk passthrough, hierarchical rollup (child → section parent),
# deduplication of sibling hits, and graceful handling of missing chunks.

from unittest.mock import AsyncMock, MagicMock

import pytest

from libs.search.hybrid.helpers import HybridSearchHelpers
from libs.search.hybrid.models import SearchResult


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _hit(chunk_id: str, score: float) -> dict:
    """Build a minimal Qdrant hit dict."""
    return {"id": chunk_id, "score": score, "payload": {"pages": [0]}}


def _row(
    chunk_id: str,
    document_id: str = "doc-001",
    raw_text: str = "sample text",
    strategy: str = "text",
    token_count: int = 10,
    parent_id: str | None = None,
    prov: dict | None = None,
) -> dict:
    """Build a minimal Postgres chunk row dict."""
    return {
        "id": chunk_id,
        "document_id": document_id,
        "raw_text": raw_text,
        "strategy": strategy,
        "token_count": token_count,
        "parent_id": parent_id,
        "prov": prov or {"pages": [0], "heading_path": ""},
        "config_hash": "cfg-abc",
        "block_ids": ["b1"],
    }


def _make_chunk_repo(rows_by_id: dict) -> MagicMock:
    """
    Build a mock ChunkRepository whose get_by_ids returns subsets of rows_by_id.

    Calls to get_by_ids(session, ids) return {id: row} for every id present in rows_by_id.
    """
    repo = MagicMock()
    async def get_by_ids(session: object, ids: list[str]) -> dict:
        return {i: rows_by_id[i] for i in ids if i in rows_by_id}
    repo.get_by_ids = get_by_ids
    return repo


# ── Flat chunk hydration ──────────────────────────────────────────────────────


class TestHydrateFlatChunks:
    """Flat chunks (no parent_id) pass through without rollup."""

    @pytest.mark.asyncio
    async def test_single_hit(self, mock_logger: MagicMock) -> None:
        """A single flat chunk hit is returned as a SearchResult."""
        row = _row("chunk-aaa", raw_text="Hello world", token_count=3)
        repo = _make_chunk_repo({"chunk-aaa": row})
        hits = [_hit("chunk-aaa", 0.95)]

        results = await HybridSearchHelpers.hydrate(None, repo, mock_logger, hits)

        assert len(results) == 1
        r = results[0]
        assert r.chunk_id == "chunk-aaa"
        assert r.score == pytest.approx(0.95)
        assert r.raw_text == "Hello world"
        assert r.token_count == 3

    @pytest.mark.asyncio
    async def test_multiple_hits_rank_order_preserved(self, mock_logger: MagicMock) -> None:
        """Multiple flat hits maintain the input rank order."""
        rows = {
            "chunk-1": _row("chunk-1", raw_text="First"),
            "chunk-2": _row("chunk-2", raw_text="Second"),
            "chunk-3": _row("chunk-3", raw_text="Third"),
        }
        repo = _make_chunk_repo(rows)
        hits = [_hit("chunk-1", 0.9), _hit("chunk-2", 0.7), _hit("chunk-3", 0.5)]

        results = await HybridSearchHelpers.hydrate(None, repo, mock_logger, hits)

        assert [r.chunk_id for r in results] == ["chunk-1", "chunk-2", "chunk-3"]
        assert results[0].score == pytest.approx(0.9)
        assert results[2].score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_prov_pages_from_row(self, mock_logger: MagicMock) -> None:
        """Pages come from the Postgres prov field, not the Qdrant payload."""
        row = _row("chunk-x", prov={"pages": [2, 3], "heading_path": ""})
        repo = _make_chunk_repo({"chunk-x": row})

        results = await HybridSearchHelpers.hydrate(None, repo, mock_logger, [_hit("chunk-x", 0.8)])

        assert results[0].pages == [2, 3]


# ── Hierarchical rollup ───────────────────────────────────────────────────────


class TestHydrateHierarchical:
    """Children are rolled up to their section parent; siblings deduplicate."""

    @pytest.mark.asyncio
    async def test_child_rolls_up_to_parent(self, mock_logger: MagicMock) -> None:
        """A child hit is replaced by its section parent row in the results."""
        parent_row = _row("parent-001", raw_text="Full section text", token_count=40)
        child_row = _row("child-001", raw_text="Paragraph one", token_count=12, parent_id="parent-001")
        repo = _make_chunk_repo({"child-001": child_row, "parent-001": parent_row})

        results = await HybridSearchHelpers.hydrate(None, repo, mock_logger, [_hit("child-001", 0.88)])

        assert len(results) == 1
        assert results[0].chunk_id == "parent-001"
        assert results[0].raw_text == "Full section text"
        # Score comes from the original child hit that triggered the lookup
        assert results[0].score == pytest.approx(0.88)

    @pytest.mark.asyncio
    async def test_sibling_deduplication(self, mock_logger: MagicMock) -> None:
        """Two children of the same parent produce only one result (highest-ranked wins)."""
        parent_row = _row("parent-001", raw_text="Full section text")
        child1 = _row("child-001", parent_id="parent-001")
        child2 = _row("child-002", parent_id="parent-001")
        repo = _make_chunk_repo({
            "child-001": child1,
            "child-002": child2,
            "parent-001": parent_row,
        })
        # child-001 ranks higher (score 0.9 > 0.6)
        hits = [_hit("child-001", 0.9), _hit("child-002", 0.6)]

        results = await HybridSearchHelpers.hydrate(None, repo, mock_logger, hits)

        assert len(results) == 1
        assert results[0].chunk_id == "parent-001"
        # The first (higher-ranked) child's score is used
        assert results[0].score == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_parent_not_found_falls_back_to_child(self, mock_logger: MagicMock) -> None:
        """When a parent row is missing from Postgres, the child row is used as-is."""
        child = _row("child-001", raw_text="Orphan paragraph", parent_id="parent-missing")
        repo = _make_chunk_repo({"child-001": child})

        results = await HybridSearchHelpers.hydrate(None, repo, mock_logger, [_hit("child-001", 0.7)])

        assert len(results) == 1
        assert results[0].chunk_id == "child-001"
        assert results[0].raw_text == "Orphan paragraph"


# ── Missing chunk ─────────────────────────────────────────────────────────────


class TestHydrateMissingChunk:
    """Qdrant hits whose chunk_id is absent from Postgres are skipped with a warning."""

    @pytest.mark.asyncio
    async def test_missing_chunk_skipped_with_warning(self, mock_logger: MagicMock) -> None:
        """A hit with no matching Postgres row is dropped; the logger emits a warning."""
        repo = _make_chunk_repo({})  # empty — nothing in Postgres

        results = await HybridSearchHelpers.hydrate(
            None, repo, mock_logger, [_hit("ghost-chunk", 0.99)]
        )

        assert results == []
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        assert "ghost-chunk" in call_args

    @pytest.mark.asyncio
    async def test_partial_miss(self, mock_logger: MagicMock) -> None:
        """Known chunks pass through; only the missing one is dropped."""
        good_row = _row("chunk-good")
        repo = _make_chunk_repo({"chunk-good": good_row})

        results = await HybridSearchHelpers.hydrate(
            None, repo, mock_logger, [_hit("chunk-ghost", 1.0), _hit("chunk-good", 0.5)]
        )

        assert len(results) == 1
        assert results[0].chunk_id == "chunk-good"


# ── UUID coercion ───────────────────────────────────────────────────────────────


class TestUuidCoercion:
    """Postgres returns UUID objects; SearchResult must expose them as strings so the
    API SearchResultItem (str fields) validates under Pydantic v2 strict typing."""

    def test_row_to_result_coerces_uuid_ids_to_str(self) -> None:
        import uuid as _uuid

        cid = _uuid.UUID("58999edb-90e1-5706-9713-04c53e758d75")
        did = _uuid.uuid4()
        row = _row("placeholder")
        row["id"] = cid
        row["document_id"] = did

        result = HybridSearchHelpers.row_to_result(row, _hit(str(cid), 0.9))

        assert result.chunk_id == str(cid)
        assert isinstance(result.chunk_id, str)
        assert result.document_id == str(did)
        assert isinstance(result.document_id, str)
