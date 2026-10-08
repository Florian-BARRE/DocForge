"""Import never hides a sparse-encoder mismatch: when the bundle cannot vouch for its content sparse
vectors (source flagged needs_reindex, or its embed baseline's sparse half is unknown / differs from the
config) they are re-encoded from the restored chunk text through the configured sparse provider. A
vouched bundle keeps its vectors verbatim (no provider call); a provider failure keeps the bundle
vectors, flags needs_reindex and never fails the import. The baseline round-trips through the bundle."""

# ====== Standard Library Imports ======
from types import SimpleNamespace
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from collection_transfer import BundleReader, CollectionExporter
from collection_transfer.manifest import CollectionContractModel
from collection_transfer.restore import CollectionImporterV1
from collection_transfer.restore.content_sparse import ImportContentSparse

# ====== Internal Project Imports ======
from shared_libs.services.db.index_embed_baseline import EmbedBaseline
from shared_libs.services.db.qdrant import SparseVec

from .conftest import COLLECTION_ID, FakeExportFacade, FakeImportFacade, make_collection

_NEW = SparseVec(indices=[42], values=[1.5])


def _contract(**overrides) -> CollectionContractModel:
    pipeline = make_collection().pipeline
    base = {
        "name": "c",
        "supported_formats": ["pdf"],
        "max_file_size_bytes": 1,
        "pipeline": pipeline,
        "indexed_embed_signature": EmbedBaseline.signature(pipeline),
    }
    return CollectionContractModel(**{**base, **overrides})


def test_needed_only_when_the_bundle_cannot_vouch_for_its_sparse_vectors() -> None:
    assert not ImportContentSparse.needed(_contract())
    assert ImportContentSparse.needed(_contract(needs_reindex=True))
    assert ImportContentSparse.needed(_contract(indexed_embed_signature=None))  # older bundle
    other = EmbedBaseline.signature({"nodes": []})
    assert ImportContentSparse.needed(_contract(indexed_embed_signature=other))


class _SignedExportFacade(FakeExportFacade):
    """An exporter source whose collection carries a matching (or given) embed baseline."""

    def __init__(self, *, needs_reindex: bool = False, signature: str | None = "match") -> None:
        super().__init__()
        self._needs_reindex = needs_reindex
        self._signature = signature

    async def get_collection(self, _collection_id):
        collection = make_collection()
        collection.needs_reindex = self._needs_reindex
        collection.indexed_embed_signature = (
            EmbedBaseline.signature(collection.pipeline)
            if self._signature == "match"
            else self._signature
        )
        return collection


async def _import(export_facade, tmp_path, reencoder) -> FakeImportFacade:
    exporter = CollectionExporter(
        export_facade, docforge_version="test", created_at="2026-01-01T00:00:00+00:00"
    )
    await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    reader = BundleReader(tmp_path / "bundle")
    reader.validate()
    facade = FakeImportFacade(content_reencoder=reencoder)
    await CollectionImporterV1(facade, reader).run()
    return facade


def _reencoder(side_effect=None) -> SimpleNamespace:
    async def _encode(point_ids: list[str]):
        return {point_id: {"content_bm25": _NEW} for point_id in point_ids}

    return SimpleNamespace(encode=AsyncMock(side_effect=side_effect or _encode))


async def test_a_vouched_bundle_keeps_its_content_sparse_verbatim(tmp_path) -> None:
    reencoder = _reencoder()
    facade = await _import(_SignedExportFacade(), tmp_path, reencoder)

    assert facade.content_reencoder_built == 0
    assert facade.points[0].sparse["content_bm25"] != _NEW
    assert facade.created.indexed_embed_signature == EmbedBaseline.signature(
        make_collection().pipeline
    )


async def test_a_flagged_source_is_reencoded_through_the_configured_provider(tmp_path) -> None:
    reencoder = _reencoder()
    facade = await _import(_SignedExportFacade(needs_reindex=True), tmp_path, reencoder)

    assert facade.points[0].sparse["content_bm25"] == _NEW
    reencoder.encode.assert_awaited_once()
    assert facade.flagged == []


async def test_an_older_bundle_without_a_baseline_is_reencoded(tmp_path) -> None:
    reencoder = _reencoder()
    facade = await _import(FakeExportFacade(), tmp_path, reencoder)

    assert facade.points[0].sparse["content_bm25"] == _NEW


async def test_a_provider_failure_keeps_the_bundle_vectors_and_flags(tmp_path) -> None:
    reencoder = _reencoder(side_effect=RuntimeError("sparse provider unreachable"))
    facade = await _import(_SignedExportFacade(needs_reindex=True), tmp_path, reencoder)

    assert len(facade.points) == 1
    assert facade.points[0].sparse["content_bm25"] != _NEW  # bundle vector kept
    assert facade.flagged == [facade.created.id]
