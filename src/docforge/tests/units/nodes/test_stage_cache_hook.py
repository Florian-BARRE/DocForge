"""StageCacheHook — the worker-side seam (before/after) over an in-memory fake facade.

Covers the hook's whole contract without a real store: a MISS returns None + records "miss" and
remembers the key; ``after`` serialises + stores + records "stored"; a subsequent MISS-then-lookup
is a HIT that deserialises the artefact, bumps the row and records "hit". Per-collection isolation is
proven by two hooks differing ONLY in collection_id (a store in one is a miss in the other). An
unknown / non-cacheable stage id is a no-op, and a store failure is swallowed (the run must survive).
"""

import uuid
from types import SimpleNamespace

from runner.cache import ArtifactCodec, StageCacheHook

from shared_libs.pipelines.ingest.nodes.parse.parser.base.io import ParserConsumes, ParserProduces
from shared_libs.public_models import IntakeResult
from shared_libs.public_models.ir.document import DocumentIR

_COLLECTION = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_COLLECTION = uuid.UUID("22222222-2222-2222-2222-222222222222")
_DOCUMENT = uuid.UUID("33333333-3333-3333-3333-333333333333")

_PARSE_BLOB = {
    "nodes": [
        {
            "id": "parse",
            "node_type": "action",
            "family": "parser",
            "kind": "docling",
            "config": {"do_ocr": True, "do_table_structure": True},
        }
    ]
}


class _FakeArtifactCacheFacade:
    """An in-memory stand-in for ArtifactCacheFacade — the hook's only I/O dependency."""

    def __init__(self) -> None:
        self.rows: dict[str, object] = {}
        self.blobs: dict[str, bytes] = {}
        self.hits: list[str] = []
        self.fail_store = False
        self.fail_load = False

    async def lookup(self, cache_key: str):
        return self.rows.get(cache_key)

    async def load_bytes(self, content_hash: str) -> bytes:
        if self.fail_load:
            raise RuntimeError("s3 read failed")
        return self.blobs[content_hash]

    async def record_hit(self, cache_key: str) -> None:
        self.hits.append(cache_key)

    async def store(self, row, data: bytes) -> None:
        if self.fail_store:
            raise RuntimeError("s3 down")
        self.rows[row.cache_key] = row
        self.blobs[row.content_hash] = data


def _hook(facade, collection_id=_COLLECTION) -> StageCacheHook:
    database = SimpleNamespace(artifact_cache=facade)
    return StageCacheHook(_PARSE_BLOB, collection_id, _DOCUMENT, database)


def _input(source_hash: str = "a" * 64) -> ParserConsumes:
    return ParserConsumes(
        source=IntakeResult(source_hash=source_hash, source_format="pdf", pdf_content=b"%PDF x")
    )


def _output(title: str = "Doc") -> ParserProduces:
    return ParserProduces(ir=DocumentIR(doc_id="d1", source_hash="a" * 64, title=title), score=0.9)


async def test_miss_then_store_then_hit_round_trips_the_artifact() -> None:
    facade = _FakeArtifactCacheFacade()
    hook = _hook(facade)
    data_in, data_out = _input(), _output()

    # 1. Cold: before is a MISS (None), after stores the artefact.
    assert await hook.before("parse", data_in) is None
    assert hook.report["parse"] == "miss"
    await hook.after("parse", data_in, data_out)
    assert hook.report["parse"] == "stored"
    assert len(facade.rows) == 1 and len(facade.blobs) == 1

    # 2. Warm: a fresh hook over the SAME store serves the artefact (a HIT), bumping the row.
    warm = _hook(facade)
    served = await warm.before("parse", data_in)
    assert isinstance(served, ParserProduces)
    assert served == data_out  # byte-identical round-trip through the store
    assert warm.report["parse"] == "hit"
    assert len(facade.hits) == 1


async def test_stored_content_hash_matches_the_serialised_bytes() -> None:
    """The stored blob's content hash IS the sha256 of the msgpack frame (dedup correctness)."""
    facade = _FakeArtifactCacheFacade()
    output = _output()
    await _hook(facade).after("parse", _input(), output)

    (row,) = facade.rows.values()
    assert row.content_hash == ArtifactCodec.sha256(ArtifactCodec.pack(output))
    assert row.collection_id == _COLLECTION and row.document_id == _DOCUMENT
    assert row.size_bytes == len(facade.blobs[row.content_hash])


async def test_per_collection_isolation_no_cross_collection_hit() -> None:
    """A stored artefact in one collection is a MISS in another (collection_id is in the key)."""
    facade = _FakeArtifactCacheFacade()
    data_in = _input()
    await _hook(facade, _COLLECTION).after("parse", data_in, _output())

    other = _hook(facade, _OTHER_COLLECTION)
    assert await other.before("parse", data_in) is None  # different collection → miss
    assert other.report["parse"] == "miss"


async def test_unknown_or_non_cacheable_stage_is_a_noop() -> None:
    """A stage id the hook did not index (not a cacheable node) is ignored by before/after."""
    facade = _FakeArtifactCacheFacade()
    hook = _hook(facade)

    assert await hook.before("chunk", _input()) is None
    await hook.after("chunk", _input(), _output())
    assert "chunk" not in hook.report and not facade.rows


async def test_store_failure_is_swallowed_and_reported() -> None:
    """A store hiccup must NOT raise into the engine — the run survives, next run recomputes."""
    facade = _FakeArtifactCacheFacade()
    facade.fail_store = True
    hook = _hook(facade)

    await hook.before("parse", _input())
    await hook.after("parse", _input(), _output())  # must not raise
    assert hook.report["parse"] == "store_failed"
    assert not facade.rows


async def test_load_failure_degrades_to_a_miss() -> None:
    """A cache row whose S3 bytes are unreadable (GC race / partial write) → MISS, never a crash.

    This is the single safety net that keeps the best-effort GC's races non-catastrophic: a pointer
    over deleted/failing bytes must serve nothing and re-run, not raise into the engine.
    """
    facade = _FakeArtifactCacheFacade()
    data_in, data_out = _input(), _output()
    await _hook(facade).after("parse", data_in, data_out)  # a real row + bytes now exist

    facade.fail_load = True  # the bytes become unreadable under a fresh hook
    warm = _hook(facade)
    assert await warm.before("parse", data_in) is None  # degrade to miss, no exception
    assert warm.report["parse"] == "miss"


async def test_corrupt_bytes_degrade_to_a_miss() -> None:
    """A cache row pointing at garbage bytes (partial write) → unpack fails → MISS, not garbage out."""
    facade = _FakeArtifactCacheFacade()
    data_in, data_out = _input(), _output()
    await _hook(facade).after("parse", data_in, data_out)
    # Corrupt the stored blob bytes in place (the row still points at this content_hash).
    (row,) = facade.rows.values()
    facade.blobs[row.content_hash] = b"not-a-valid-msgpack-frame"

    warm = _hook(facade)
    assert await warm.before("parse", data_in) is None
    assert warm.report["parse"] == "miss"
