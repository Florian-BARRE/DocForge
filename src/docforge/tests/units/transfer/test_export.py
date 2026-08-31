"""CollectionExporter: the streamed bundle shaping over a mocked store gateway — id preservation,
metadata keyed by field NAME (not the server-local int id), the dense/sparse point split, blob
dedup, and a manifest whose counts + checksums make the produced tree self-validating."""

import json

from collection_transfer import BundleReader, CollectionExporter
from collection_transfer.paths import BundlePaths

from .conftest import CHUNK_ID, COLLECTION_ID, DENSE_DIM, DOC_ID, ORIGINAL_HASH, PDF_HASH


async def _build(export_facade, tmp_path):
    exporter = CollectionExporter(
        export_facade, docforge_version="test", created_at="2026-01-01T00:00:00+00:00"
    )
    manifest = await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    return manifest, tmp_path / "bundle"


def _rows(root, rel_path):
    return [json.loads(line) for line in (root / rel_path).read_text("utf-8").splitlines() if line]


async def test_manifest_counts_and_dense_dim(export_facade, tmp_path) -> None:
    manifest, _ = await _build(export_facade, tmp_path)
    assert manifest.dense_dim == DENSE_DIM
    assert manifest.counts.documents == 1
    assert manifest.counts.chunks == 1
    assert manifest.counts.points == 1
    assert manifest.counts.blobs == 2
    assert manifest.counts.metadata_fields == 2


async def test_chunk_id_is_preserved_verbatim(export_facade, tmp_path) -> None:
    _, root = await _build(export_facade, tmp_path)
    chunks = _rows(root, BundlePaths.CHUNKS)
    assert chunks[0]["id"] == str(CHUNK_ID)  # equals the Qdrant point id — must not be re-minted


async def test_metadata_travels_by_field_name_not_id(export_facade, tmp_path) -> None:
    _, root = await _build(export_facade, tmp_path)
    doc_meta = _rows(root, BundlePaths.DOCUMENT_METADATA)[0]
    assert doc_meta["field_name"] == "author"
    assert "field_id" not in doc_meta  # the autoincrement key is dropped on purpose
    chunk_meta = _rows(root, BundlePaths.CHUNK_METADATA)[0]
    assert chunk_meta["field_name"] == "topic"
    assert chunk_meta["chunk_id"] == str(CHUNK_ID)


async def test_point_splits_dense_and_sparse(export_facade, tmp_path) -> None:
    _, root = await _build(export_facade, tmp_path)
    point = _rows(root, BundlePaths.POINTS)[0]
    assert point["id"] == str(CHUNK_ID)
    assert point["vectors"]["content_dense"] == [0.1, 0.2, 0.3, 0.4]
    assert point["vectors"]["content_bm25"] == {"indices": [1, 5], "values": [0.7, 0.3]}
    assert point["payload"]["document_id"] == str(DOC_ID)


async def test_blob_bytes_deduped_one_file_per_hash(export_facade, tmp_path) -> None:
    _, root = await _build(export_facade, tmp_path)
    blob_files = {p.name for p in (root / BundlePaths.BLOB_DIR).iterdir()}
    assert blob_files == {ORIGINAL_HASH, PDF_HASH}
    assert len(_rows(root, BundlePaths.BLOBS)) == 2


async def test_produced_bundle_self_validates(export_facade, tmp_path) -> None:
    _, root = await _build(export_facade, tmp_path)
    # Every checksum the exporter recorded must match what the reader recomputes.
    manifest = BundleReader(root).validate()
    assert manifest.counts.points == 1
