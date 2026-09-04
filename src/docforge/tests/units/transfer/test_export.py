"""CollectionExporter: the streamed bundle shaping over a mocked store gateway — id preservation,
metadata keyed by field NAME (not the server-local int id), the dense/sparse point split, blob
dedup, and a manifest whose counts + checksums make the produced tree self-validating."""

import json
from types import SimpleNamespace

import pytest
from collection_transfer import BundleReader, CollectionExporter
from collection_transfer.export import CollectionExportError
from collection_transfer.paths import BundlePaths

from .conftest import (
    CHUNK_ID,
    COLLECTION_ID,
    DENSE_DIM,
    DOC_ID,
    ORIGINAL_HASH,
    PDF_HASH,
    FakeExportFacade,
    make_blob_rows,
    make_point_record,
)

# A point whose id matches NO live chunk in the bundle — an orphan the importer would drop anyway.
ORPHAN_POINT_ID = "99999999-9999-9999-9999-999999999999"


class SnapshotDriftExportFacade(FakeExportFacade):
    """A live re-query of blob hashes would EXPLODE — the exporter must derive them from the snapshot.

    ``collect_blob_hashes`` is the OLD live re-query path; the snapshot-consistent exporter must never
    call it (the blob set now comes from the document rows already written). A call here is a bug.
    """

    async def collect_blob_hashes(self, _collection_id):
        raise AssertionError(
            "collect_blob_hashes must not be called — blobs come from the snapshot"
        )


class MissingBlobRowExportFacade(FakeExportFacade):
    """The PDF blob's REGISTRY ROW vanished (a concurrent delete raced the document pass)."""

    async def get_blob_rows(self, _hashes):
        return [make_blob_rows()[0]]  # only the ORIGINAL row survives; the PDF row is gone


class MissingBlobBytesExportFacade(FakeExportFacade):
    """The blob's S3 OBJECT vanished between the registry read and the byte stream."""

    async def read_blob_bytes(self, s3_key):
        raise FileNotFoundError(f"object {s3_key} not found")


class OrphanPointExportFacade(FakeExportFacade):
    """Scrolls the live point PLUS one orphan point (a vector whose chunk row is gone)."""

    async def scroll_points(self, _collection_id, _batch_size=256):
        yield make_point_record()  # live: id == CHUNK_ID
        yield SimpleNamespace(
            id=ORPHAN_POINT_ID,
            vector={"content_dense": [0.0, 0.0, 0.0, 0.0]},
            payload={},
        )


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


async def test_orphan_points_are_dropped_from_count_and_bundle(tmp_path) -> None:
    exporter = CollectionExporter(
        OrphanPointExportFacade(),
        docforge_version="test",
        created_at="2026-01-01T00:00:00+00:00",
    )
    manifest = await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    # Only the point backed by a live chunk is emitted + counted, so counts.points equals the
    # vector count the import will actually restore (no phantom "20 points lost" on comparison).
    assert manifest.counts.points == 1
    points = _rows(tmp_path / "bundle", BundlePaths.POINTS)
    assert [point["id"] for point in points] == [str(CHUNK_ID)]


async def test_produced_bundle_self_validates(export_facade, tmp_path) -> None:
    _, root = await _build(export_facade, tmp_path)
    # Every checksum the exporter recorded must match what the reader recomputes.
    manifest = BundleReader(root).validate()
    assert manifest.counts.points == 1


async def test_blob_set_is_derived_from_the_document_snapshot_not_a_live_requery(tmp_path) -> None:
    # The exporter must NOT re-query the collection's blob hashes live (that could disagree with the
    # documents already written); it derives them from the snapshot rows. The facade's live re-query
    # raises if called, yet the export still emits exactly the snapshot-referenced blobs.
    manifest, root = await _build(SnapshotDriftExportFacade(), tmp_path)
    blob_files = {p.name for p in (root / BundlePaths.BLOB_DIR).iterdir()}
    assert blob_files == {ORIGINAL_HASH, PDF_HASH}  # doc.source_hash + doc.pdf_blob_hash — no more
    assert manifest.counts.blobs == 2


async def test_export_aborts_loudly_when_a_referenced_blob_row_vanished(tmp_path) -> None:
    exporter = CollectionExporter(
        MissingBlobRowExportFacade(),
        docforge_version="test",
        created_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(CollectionExportError) as excinfo:
        await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    message = str(excinfo.value)
    # The error names the vanished blob AND the document that referenced it — never a silent drop.
    assert PDF_HASH in message
    assert "demo.pdf" in message  # the referencing document's filename (see make_document)


async def test_export_aborts_loudly_when_a_referenced_blob_object_vanished(tmp_path) -> None:
    exporter = CollectionExporter(
        MissingBlobBytesExportFacade(),
        docforge_version="test",
        created_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(CollectionExportError) as excinfo:
        await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    # A missing S3 object also aborts loudly, naming the referencing document — no corrupt bundle.
    assert "demo.pdf" in str(excinfo.value)
