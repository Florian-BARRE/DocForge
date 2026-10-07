"""EXECUTES the filter-operator conditions against a real Qdrant (dev store, port 10043): the pure
build_match_conditions → QdrantSearchApi._to_filter translation of `not`/`not_in` (nested must_not,
every listed case variant excluded), `exists` true/false (IsEmpty: absent key, null and [] all count as
"no value"), `in`, full-text `contains`, and a DATETIME range over a DATETIME payload index holding the
ISO strings admission accepts. Skipped when Qdrant is not reachable."""

# ====== Standard Library Imports ======
import socket
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from qdrant_client import AsyncQdrantClient, models

# ====== Internal Project Imports ======
from shared_libs.services.db.qdrant import QdrantSearchApi, build_match_conditions

pytestmark = pytest.mark.db

QDRANT_URL = "http://127.0.0.1:10043"

# id → payload. 3 has no `author` key, 4 a null author, 5 an empty keyword list.
_POINTS: dict[int, dict] = {
    0: {
        "author": "Smith",
        "keywords": ["alpha"],
        "summary": "audit of rights",
        "pub": "2024-01-15",
    },
    1: {
        "author": "smith",
        "keywords": ["beta"],
        "summary": "breach report",
        "pub": "2024-01-20T10:00:00",
    },
    2: {
        "author": "Jones",
        "keywords": ["alpha", "beta"],
        "summary": "audit plan",
        "pub": "2024-03-01T00:00:00+02:00",
    },
    3: {"keywords": ["gamma"], "summary": "misc", "pub": "2023-12-31 23:00:00"},
    4: {"author": None, "keywords": ["alpha"], "summary": "rights", "pub": "2024-02-01"},
    5: {"author": "Lee", "keywords": [], "summary": "empty"},
}


def _qdrant_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 10043), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.fixture
async def scratch() -> AsyncIterator[tuple[AsyncQdrantClient, str]]:
    if not _qdrant_up():
        pytest.skip("Qdrant (127.0.0.1:10043) unreachable")
    client = AsyncQdrantClient(url=QDRANT_URL)
    name = f"test_filter_ops_{uuid.uuid4().hex[:8]}"
    await client.create_collection(
        name, vectors_config={"d": models.VectorParams(size=2, distance=models.Distance.COSINE)}
    )
    try:
        for key, schema in (
            ("author", models.PayloadSchemaType.KEYWORD),
            ("keywords", models.PayloadSchemaType.KEYWORD),
            ("summary", models.PayloadSchemaType.TEXT),
            ("pub", models.PayloadSchemaType.DATETIME),
        ):
            await client.create_payload_index(name, key, field_schema=schema)
        await client.upsert(
            name,
            [
                models.PointStruct(id=pid, vector={"d": [1.0, 0.5]}, payload=payload)
                for pid, payload in _POINTS.items()
            ],
            wait=True,
        )
        yield client, name
    finally:
        await client.delete_collection(name)
        await client.close()


async def _ids(scratch, filters: dict, text_fields: tuple[str, ...] = ()) -> list[int]:
    client, name = scratch
    query_filter = QdrantSearchApi._to_filter(build_match_conditions(filters, text_fields), [])
    points, _ = await client.scroll(name, scroll_filter=query_filter, limit=100)
    return sorted(int(point.id) for point in points)


async def test_not_in_excludes_every_listed_case_variant(scratch) -> None:
    # The resolver turns {"not": "smith"} into {"not_in": ["Smith", "smith"]}.
    assert await _ids(scratch, {"author": {"not_in": ["Smith", "smith"]}}) == [2, 3, 4, 5]
    assert await _ids(scratch, {"author": {"not": "Jones"}}) == [0, 1, 3, 4, 5]


async def test_exists_true_and_false(scratch) -> None:
    assert await _ids(scratch, {"author": {"exists": True}}) == [0, 1, 2, 5]
    assert await _ids(scratch, {"author": {"exists": False}}) == [3, 4]
    assert await _ids(scratch, {"keywords": {"exists": False}}) == [5]


async def test_in_and_not_on_a_keyword_list(scratch) -> None:
    assert await _ids(scratch, {"keywords": {"in": ["beta"]}}) == [1, 2]
    assert await _ids(scratch, {"keywords": {"not": "alpha"}}) == [1, 3, 5]


async def test_contains_on_a_text_field_is_full_text(scratch) -> None:
    assert await _ids(scratch, {"summary": {"contains": "audit"}}, ("summary",)) == [0, 2]
    assert await _ids(scratch, {"summary": {"not": "audit"}}, ("summary",)) == [1, 3, 4, 5]


async def test_datetime_range_over_a_datetime_index(scratch) -> None:
    # Date-only, naive, offset and space-separated ISO strings are all indexed as datetimes.
    january = {"pub": {"gte": "2024-01-01", "lt": "2024-02-01"}}
    assert await _ids(scratch, january) == [0, 1]
    assert await _ids(scratch, {"pub": {"lt": "2024-01-01T00:00:00"}}) == [3]
    assert await _ids(scratch, {"pub": {"gte": "2024-02-01T00:00:00Z"}}) == [2, 4]


async def test_operators_and_together(scratch) -> None:
    filters = {
        "keywords": {"in": ["alpha"]},
        "author": {"exists": True},
        "pub": {"lt": "2024-02-01"},
    }
    assert await _ids(scratch, filters) == [0]
