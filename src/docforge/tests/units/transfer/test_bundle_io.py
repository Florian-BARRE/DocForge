"""BundleWriter / BundleArchive / BundleReader: the on-disk contract — streamed JSONL + deduped
blob bytes, tar(+zstd) round-trip, and the fail-fast integrity gates (per-file checksum + blob
content-address). These are the guards that make an import refuse a tampered/truncated bundle."""

import hashlib

import pytest
from collection_transfer import (
    COMPRESSION_NONE,
    COMPRESSION_ZSTD,
    BundleArchive,
    BundleReader,
    BundleValidationError,
    BundleWriter,
)
from collection_transfer.manifest import (
    CURRENT_FORMAT_VERSION,
    CollectionContractModel,
    CollectionRef,
    ExportManifest,
    TransferCounts,
)
from collection_transfer.paths import BundlePaths


def _write_minimal_bundle(root, *, compression=COMPRESSION_NONE) -> ExportManifest:
    """Lay a tiny valid bundle tree (one doc row, one deduped blob) and return its manifest."""
    writer = BundleWriter(root)
    writer.write_collection(
        CollectionContractModel(name="n", supported_formats=["pdf"], max_file_size_bytes=1)
    )
    with writer.sink(BundlePaths.DOCUMENTS) as sink:
        sink.write({"id": "doc-1", "filename": "a.pdf"})
        sink.write({"id": "doc-2", "filename": "b.pdf"})
    data = b"hello-bytes"
    digest = hashlib.sha256(data).hexdigest()
    assert writer.write_blob(digest, data) is True
    assert writer.write_blob(digest, data) is False  # deduped: second write is a no-op
    manifest = ExportManifest(
        format_version=CURRENT_FORMAT_VERSION,
        docforge_version="test",
        created_at="2026-01-01T00:00:00+00:00",
        collection=CollectionRef(id="c", name="n"),
        dense_dim=4,
        compression=compression,
        counts=TransferCounts(documents=2, blobs=writer.blob_count),
    )
    writer.write_manifest(manifest)
    return manifest


def test_writer_dedups_blob_to_a_single_file(tmp_path) -> None:
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    blob_files = list((root / BundlePaths.BLOB_DIR).iterdir())
    assert len(blob_files) == 1  # written twice, stored once


def test_reader_validates_and_streams_rows(tmp_path) -> None:
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    reader = BundleReader(root)
    manifest = reader.validate()
    assert manifest.counts.documents == 2
    rows = list(reader.iter_rows(BundlePaths.DOCUMENTS))
    assert [row["id"] for row in rows] == ["doc-1", "doc-2"]


def test_reader_rejects_a_tampered_data_file(tmp_path) -> None:
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    # Corrupt a checksummed file AFTER the manifest was written.
    (root / BundlePaths.DOCUMENTS).write_text('{"id": "hacked"}\n', encoding="utf-8")
    with pytest.raises(BundleValidationError):
        BundleReader(root).validate()


def test_reader_rejects_blob_content_address_mismatch(tmp_path) -> None:
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    reader = BundleReader(root)
    reader.validate()
    (root / BundlePaths.blob_path("f" * 64)).write_bytes(b"not-matching")
    with pytest.raises(BundleValidationError):
        reader.read_blob("f" * 64)


@pytest.mark.parametrize("compression", [COMPRESSION_NONE, COMPRESSION_ZSTD])
def test_archive_pack_unpack_round_trip(tmp_path, compression) -> None:
    root = tmp_path / "bundle"
    _write_minimal_bundle(root, compression=compression)
    archive = tmp_path / "out.dcexport"
    BundleArchive.pack(root, archive, compression)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    BundleArchive.unpack(archive, extracted)
    manifest = BundleReader(extracted).validate()
    assert manifest.compression == compression
    assert manifest.counts.documents == 2


@pytest.mark.parametrize("compression", [COMPRESSION_NONE, COMPRESSION_ZSTD])
def test_unpack_refuses_a_bundle_that_exceeds_the_uncompressed_ceiling(tmp_path, compression) -> None:
    """Decompression-bomb guard: extraction aborts once the cumulative member size crosses the cap,

    so a high-ratio bundle can never fill the worker's disk. Checked for both codecs.
    """
    root = tmp_path / "bundle"
    _write_minimal_bundle(root, compression=compression)
    archive = tmp_path / "out.dcexport"
    BundleArchive.pack(root, archive, compression)
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    with pytest.raises(ValueError, match="size ceiling"):
        BundleArchive.unpack(archive, extracted, max_uncompressed_bytes=10)


def test_unpack_refuses_a_bundle_with_too_many_members(tmp_path) -> None:
    """The member-count ceiling bounds inode/handle exhaustion independently of total size."""
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    archive = tmp_path / "out.dcexport"
    BundleArchive.pack(root, archive, COMPRESSION_NONE)
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    with pytest.raises(ValueError, match="member-count ceiling"):
        BundleArchive.unpack(archive, extracted, max_members=1)


def test_unpack_allows_a_normal_bundle_under_generous_caps(tmp_path) -> None:
    """A legitimate bundle extracts cleanly when the caps are set the way the import task sets them."""
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    archive = tmp_path / "out.dcexport"
    BundleArchive.pack(root, archive, COMPRESSION_NONE)
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    # Same shape the worker uses: a multiple of the compressed size + a high member cap.
    cap = archive.stat().st_size * 100
    BundleArchive.unpack(archive, extracted, max_uncompressed_bytes=cap, max_members=500_000)
    assert BundleReader(extracted).validate().counts.documents == 2


def test_reader_rejects_unsupported_format_version(tmp_path) -> None:
    root = tmp_path / "bundle"
    _write_minimal_bundle(root)
    manifest_path = root / BundlePaths.MANIFEST
    manifest_path.write_text(
        manifest_path.read_text("utf-8").replace('"format_version": 1', '"format_version": 999'),
        encoding="utf-8",
    )
    with pytest.raises(BundleValidationError):
        BundleReader(root).validate()
