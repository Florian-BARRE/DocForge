"""CollectionImporterV1: the restore is the exporter in reverse — a real bundle is produced by the
exporter, then imported through a recording fake gateway to prove the id-remap (metadata int id
re-linked by field NAME), the PRESERVED chunk id (== Qdrant point id) and block id, the collision
rename, and the whole-collection rollback on a mid-restore failure."""

import pytest
from collection_transfer import BundleReader, CollectionExporter
from collection_transfer.restore import CollectionImportError, CollectionImporterV1

from .conftest import BLOCK_ID, CHUNK_ID, COLLECTION_ID, DENSE_DIM, DOC_ID, FakeImportFacade


async def _bundle(export_facade, tmp_path) -> BundleReader:
    """Produce a real bundle with the exporter, then a validated reader over its tree."""
    exporter = CollectionExporter(
        export_facade, docforge_version="test", created_at="2026-01-01T00:00:00+00:00"
    )
    await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    reader = BundleReader(tmp_path / "bundle")
    reader.validate()
    return reader


async def test_import_remaps_ids_consistently(export_facade, tmp_path) -> None:
    reader = await _bundle(export_facade, tmp_path)
    facade = FakeImportFacade()
    importer = CollectionImporterV1(facade, reader)

    result = await importer.run()

    # A fresh collection with a fresh UUID and the bundle's name (no collision here).
    assert result.collection_name == "DemoCollection"
    assert facade.created is not None and facade.created.id == result.collection_id

    document = facade.restored["Document"][0]
    chunk = facade.restored["Chunk"][0]
    block = facade.restored["Block"][0]
    chunk_block = facade.restored["ChunkBlock"][0]

    # Every id is REGENERATED (new != old) so the bundle restores even onto its origin server.
    assert document.id != DOC_ID
    assert chunk.id != CHUNK_ID
    assert block.id != BLOCK_ID
    # ...and rewritten CONSISTENTLY: every FK resolves to the freshly minted ids.
    assert document.collection_id == result.collection_id
    assert chunk.document_id == document.id
    assert block.document_id == document.id
    assert block.id.startswith(f"{document.id}:")  # block id re-namespaced onto the new doc id
    assert chunk_block.chunk_id == chunk.id
    assert chunk_block.block_id == block.id
    # Metadata re-links by NAME to the freshly minted field ids (author→100, topic→101) + new owner.
    doc_meta = facade.restored["DocumentMetadata"][0]
    chunk_meta = facade.restored["ChunkMetadata"][0]
    assert doc_meta.field_id == 100 and doc_meta.document_id == document.id
    assert chunk_meta.field_id == 101 and chunk_meta.chunk_id == chunk.id


async def test_import_upserts_points_under_remapped_chunk_id(export_facade, tmp_path) -> None:
    reader = await _bundle(export_facade, tmp_path)
    facade = FakeImportFacade()

    await CollectionImporterV1(facade, reader).run()

    chunk = facade.restored["Chunk"][0]
    document = facade.restored["Document"][0]
    assert facade.ensured_dense_dim == DENSE_DIM
    assert len(facade.points) == 1
    point = facade.points[0]
    # The point id is the chunk's NEW id (chunk.id == point.id still holds), not the old one.
    assert point.point_id == str(chunk.id)
    assert point.point_id != str(CHUNK_ID)
    # The payload's document_id is remapped to the new document too.
    assert point.payload["document_id"] == str(document.id)
    assert "content_dense" in point.dense
    assert "content_bm25" in point.sparse
    # Blobs re-registered + re-uploaded (deduped set of two) — content hashes NOT remapped.
    assert len(facade.blob_objects) == 2
    assert len(facade.blob_rows) == 2


async def test_import_renames_on_name_collision(export_facade, tmp_path) -> None:
    reader = await _bundle(export_facade, tmp_path)
    facade = FakeImportFacade(existing_names={"DemoCollection"})

    result = await CollectionImporterV1(facade, reader).run()

    assert result.collection_name == "DemoCollection (imported)"


async def test_import_rolls_back_the_new_collection_on_failure(export_facade, tmp_path) -> None:
    reader = await _bundle(export_facade, tmp_path)
    facade = FakeImportFacade(fail_on="Chunk")  # blow up midway through the restore

    with pytest.raises(CollectionImportError):
        await CollectionImporterV1(facade, reader).run()

    # The half-built collection was deleted; a pre-existing collection would never be touched.
    assert facade.created is not None
    assert facade.rolled_back == [facade.created.id]


async def test_import_pins_blob_s3_key_to_content_hash_ignoring_a_tampered_key() -> None:
    """A tampered bundle s3_key (pointing at a victim object) is ignored — the upload and the

    registered row are both pinned to the content hash, so an import can only ever write its own
    content address (closes the arbitrary-S3-overwrite vector).
    """
    from collection_transfer.paths import BundlePaths
    from collection_transfer.restore import CollectionImporterV1

    from .conftest import FakeImportFacade

    attacker_bytes = b"attacker-controlled bytes"
    content_hash = "aaaa1111"  # stands in for sha256(attacker_bytes)
    victim_key = "victim0000"  # another tenant's object the attacker aimed to overwrite

    class _FakeReader:
        """Yields ONE blob row whose s3_key != content_hash, plus its bytes."""

        def iter_rows(self, path):
            assert path == BundlePaths.BLOBS
            yield {
                "content_hash": content_hash,
                "s3_key": victim_key,  # the tamper: a foreign key
                "mime_type": "application/octet-stream",
                "size_bytes": len(attacker_bytes),
                "kind": "original",
            }

        def read_blob(self, requested_hash):
            assert requested_hash == content_hash
            return attacker_bytes

    facade = FakeImportFacade()
    importer = CollectionImporterV1(facade, _FakeReader())

    await importer._restore_blobs()

    # The uploaded object is keyed by the content hash, NOT the tampered victim key.
    assert [obj.key for obj in facade.blob_objects] == [content_hash]
    # ...and the registered row's s3_key was rewritten to match — no dangling foreign pointer.
    assert [row.s3_key for row in facade.blob_rows] == [content_hash]
    assert victim_key not in {obj.key for obj in facade.blob_objects}


async def test_import_streams_blobs_in_bounded_batches_never_the_whole_bundle() -> None:
    """The blob restore must flush in bounded byte-budget batches — peak resident memory is one batch,
    NOT the whole bundle. Several blobs whose total FAR exceeds the budget must trigger MULTIPLE
    store_blobs flushes, each bounded by ~the budget (never a single all-blobs call).
    """
    import hashlib

    from collection_transfer.paths import BundlePaths
    from collection_transfer.restore import CollectionImporterV1

    from .conftest import FakeImportFacade

    blob_size = 100
    budget = 150  # each batch may hold at most two 100-byte blobs before it flushes
    blob_count = 5  # 500 bytes total — ~3.3x the budget, so it CANNOT ride in one buffer
    payloads = {
        hashlib.sha256(f"blob-{index}".encode()).hexdigest(): b"x" * blob_size
        for index in range(blob_count)
    }

    class _FakeReader:
        """Yields ``blob_count`` blob rows (s3_key already == content_hash) + their bytes."""

        def iter_rows(self, path):
            assert path == BundlePaths.BLOBS
            for content_hash in payloads:
                yield {
                    "content_hash": content_hash,
                    "s3_key": content_hash,
                    "mime_type": "application/octet-stream",
                    "size_bytes": blob_size,
                    "kind": "original",
                }

        def read_blob(self, content_hash):
            return payloads[content_hash]

    class _RecordingImportFacade(FakeImportFacade):
        """Records the byte size of every store_blobs flush so the test can bound peak buffering."""

        def __init__(self) -> None:
            super().__init__()
            self.flush_byte_sizes: list[int] = []

        async def store_blobs(self, objects, rows):
            objects, rows = list(objects), list(rows)
            self.flush_byte_sizes.append(sum(len(obj.data) for obj in objects))
            await super().store_blobs(objects, rows)

    facade = _RecordingImportFacade()
    importer = CollectionImporterV1(facade, _FakeReader(), blob_batch_bytes=budget)

    await importer._restore_blobs()

    # Streamed, not one-shot: more than one flush, and no flush ever held the whole bundle.
    assert len(facade.flush_byte_sizes) > 1
    total_bytes = blob_size * blob_count
    peak_buffered = max(facade.flush_byte_sizes)
    assert peak_buffered < total_bytes  # never the whole bundle resident at once
    assert peak_buffered <= budget + blob_size  # bounded by the budget + at most one in-flight blob
    # Every blob still lands — the batching loses nothing.
    assert len(facade.blob_objects) == blob_count
    assert len(facade.blob_rows) == blob_count
    assert sum(facade.flush_byte_sizes) == total_bytes
