"""The stage-cache serialisation + key composition (ArtifactCodec + CacheKeyBuilder).

Two guarantees a wrong hit would break: (1) a cached artefact round-trips BYTE-IDENTICALLY — even
binary figure-crop bytes and tuple bboxes survive the msgpack frame + model re-validation; (2) the
Merkle key changes whenever ANY of its five components change — the upstream input, the whole config
subtree, the node identity, the CACHE_VERSION/epoch, and the collection_id (the per-collection
isolation). Identical inputs in the SAME collection are the only thing that collides.
"""

import uuid

from runner.cache import ArtifactCodec, CacheKeyBuilder

from shared_libs.pipelines.ingest.nodes.parse.parser.base.io import ParserConsumes, ParserProduces
from shared_libs.public_models import IntakeResult
from shared_libs.public_models.ir.block import Block
from shared_libs.public_models.ir.document import DocumentIR
from shared_libs.public_models.ir.enums import BlockType, FigureKind
from shared_libs.public_models.ir.figure import FigureEnrichment
from shared_libs.public_models.ir.provenance import Provenance

_COLLECTION = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_COLLECTION = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _parser_produces() -> ParserProduces:
    """A realistic parse output: a text block + a FIGURE block carrying binary crop bytes."""
    ir = DocumentIR(
        doc_id="d1",
        source_hash="a" * 64,
        title="Doc",
        n_pages=1,
        blocks=[
            Block(
                id="b1",
                block_type=BlockType.PARAGRAPH,
                provenance=Provenance(page=0, bbox=(0.0, 0.0, 1.0, 0.5)),
                reading_order=0,
                text="hello world",
            ),
            Block(
                id="b2",
                block_type=BlockType.FIGURE,
                provenance=Provenance(page=0, bbox=(0.0, 0.5, 1.0, 1.0)),
                reading_order=1,
                figure=FigureEnrichment(kind=FigureKind.CHART, crop=bytes(range(256))),
            ),
        ],
    )
    return ParserProduces(ir=ir, score=0.87)


def _intake(source_hash: str = "a" * 64) -> ParserConsumes:
    """A parser input carrying real PDF-view bytes (the upstream artefact the stage consumes)."""
    return ParserConsumes(
        source=IntakeResult(
            source_hash=source_hash,
            source_format="pdf",
            pdf_content=b"%PDF-1.7 binary...\x00\x01",
            page_count=1,
        )
    )


def _key(**overrides) -> str:
    """Build a cache key with sensible defaults, overriding one component at a time."""
    params = {
        "family": "parser",
        "kind": "docling",
        "cache_version": "1",
        "config": {"do_ocr": True, "do_table_structure": True},
        "resolved_input": _intake(),
        "collection_id": _COLLECTION,
    }
    params.update(overrides)
    return CacheKeyBuilder.build(**params)


# ── codec byte-identity ────────────────────────────────────────────────────────────────────────
def test_codec_round_trips_a_parse_output_byte_identically() -> None:
    """pack → unpack reproduces the exact model, including binary crop bytes and tuple bboxes."""
    original = _parser_produces()
    restored = ArtifactCodec.unpack(ArtifactCodec.pack(original), ParserProduces)

    assert isinstance(restored, ParserProduces)
    assert restored == original  # full structural equality (bytes, enums, tuples all survive)
    assert restored.ir.blocks[1].figure.crop == bytes(range(256))
    assert restored.model_dump() == original.model_dump()


def test_codec_pack_is_deterministic() -> None:
    """The same model packs to identical bytes (a stable content hash for dedup)."""
    a, b = ArtifactCodec.pack(_parser_produces()), ArtifactCodec.pack(_parser_produces())
    assert a == b
    assert ArtifactCodec.sha256(a) == ArtifactCodec.sha256(b)


# ── key composition ──────────────────────────────────────────────────────────────────────────--
def test_identical_everything_yields_the_same_key() -> None:
    """A stable, reproducible key is the whole point — same inputs, same key."""
    assert _key() == _key()


def test_a_different_collection_yields_a_different_key() -> None:
    """PER-COLLECTION ISOLATION: the collection_id is folded in, so no cross-collection sharing."""
    assert _key(collection_id=_COLLECTION) != _key(collection_id=_OTHER_COLLECTION)


def test_a_config_change_yields_a_different_key() -> None:
    """Any change in the normalised config subtree invalidates the key (whole subtree, no subset)."""
    assert _key(config={"do_ocr": True}) != _key(config={"do_ocr": False})


def test_a_kind_change_yields_a_different_key() -> None:
    """Swapping the provider (family/kind identity) changes the key."""
    assert _key(kind="docling") != _key(kind="granite_docling")


def test_a_cache_version_bump_yields_a_different_key() -> None:
    """Bumping a node's CACHE_VERSION invalidates every prior artefact for it."""
    assert _key(cache_version="1") != _key(cache_version="2")


def test_a_different_upstream_input_yields_a_different_key() -> None:
    """The input fingerprint is the REAL upstream content — a different source → a different key."""
    assert _key(resolved_input=_intake("a" * 64)) != _key(resolved_input=_intake("b" * 64))


def test_the_key_is_a_sha256_hex_digest() -> None:
    """The composed key is a 64-char hex sha256 (fits the artifact_cache PK width)."""
    key = _key()
    assert len(key) == 64 and int(key, 16) >= 0
