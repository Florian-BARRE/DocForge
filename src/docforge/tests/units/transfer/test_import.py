"""CollectionImporterV1: the restore is the exporter in reverse — a real bundle is produced by the
exporter, then imported through a recording fake gateway to prove the id-REMAP (every id regenerated,
metadata int id re-linked by field NAME, the chunk id kept == its Qdrant point id THROUGH the remap,
the block id re-namespaced onto the new doc), the collision rename, the manifest-count reconciliation,
consistent dangling-reference handling, and the whole-collection rollback on a mid-restore failure."""

import json
import uuid
from types import SimpleNamespace

import pytest
from collection_transfer import BundleReader, CollectionExporter
from collection_transfer.manifest import CollectionContractModel
from collection_transfer.restore import (
    CollectionImportError,
    CollectionImporterV1,
    RemapContext,
    RowDeserializer,
)

from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.search import SearchPipeline

from .conftest import (
    BLOCK_ID,
    CHUNK_ID,
    COLLECTION_ID,
    DENSE_DIM,
    DOC_ID,
    FakeExportFacade,
    FakeImportFacade,
)


def _contract(*, pipeline: dict, search: dict) -> CollectionContractModel:
    """A minimal collection contract carrying the graph blobs the import-time validator checks."""
    return CollectionContractModel(
        name="c",
        supported_formats=["pdf"],
        max_file_size_bytes=1024,
        pipeline=pipeline,
        search=search,
    )


# A blob naming a node kind the registry does not know — a BuildError at build time.
_UNBUILDABLE = {
    "id": "g",
    "nodes": [{"id": "n", "family": "parser", "kind": "does_not_exist", "config": {}}],
    "transitions": [],
    "bindings": {},
}


def test_import_validation_rejects_malformed_pipeline_blob() -> None:
    """A malformed/unbuildable pipeline blob aborts the import LOUDLY, naming the pipeline blob."""
    importer = CollectionImporterV1(FakeImportFacade(), object())

    with pytest.raises(CollectionImportError) as exc:
        importer._validate_contract_blobs(_contract(pipeline=_UNBUILDABLE, search={}))

    assert "pipeline blob" in str(exc.value)


def test_import_validation_rejects_malformed_search_blob() -> None:
    """A non-empty malformed search blob aborts the import LOUDLY, naming the search blob (the
    pipeline being valid, so the failure is unambiguously attributed to search)."""
    valid_pipeline = IngestPipeline.light_blob().model_dump(mode="json")
    importer = CollectionImporterV1(FakeImportFacade(), object())

    with pytest.raises(CollectionImportError) as exc:
        importer._validate_contract_blobs(_contract(pipeline=valid_pipeline, search=_UNBUILDABLE))

    assert "search blob" in str(exc.value)


def test_import_validation_rejects_non_search_topology() -> None:
    """A structurally-valid graph that is NOT a search pipeline (no SearchResult terminal) is
    rejected — the shared terminal contract runs on import exactly as at the app write boundary."""
    valid_pipeline = IngestPipeline.light_blob().model_dump(mode="json")
    non_search = SearchPipeline.default_blob().model_dump(mode="json")
    non_search["nodes"] = [n for n in non_search["nodes"] if n["id"] != "deliver"]
    non_search["transitions"] = [
        t for t in non_search["transitions"] if t["to_node_id"] != "deliver"
    ]
    non_search["bindings"] = {k: v for k, v in non_search["bindings"].items() if k != "deliver"}
    importer = CollectionImporterV1(FakeImportFacade(), object())

    with pytest.raises(CollectionImportError) as exc:
        importer._validate_contract_blobs(_contract(pipeline=valid_pipeline, search=non_search))

    assert "search blob" in str(exc.value)
    assert "not a valid search pipeline" in str(exc.value)


def test_import_validation_accepts_valid_pipeline_and_empty_search() -> None:
    """A valid pipeline with the empty ``{}`` search default (the stock search) validates cleanly."""
    valid_pipeline = IngestPipeline.light_blob().model_dump(mode="json")
    importer = CollectionImporterV1(FakeImportFacade(), object())

    # No raise — the empty search sentinel is left untouched (uses the built-in search pipeline).
    importer._validate_contract_blobs(_contract(pipeline=valid_pipeline, search={}))


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


# ─────────────────────── Item 1 — manifest count reconciliation ───────────────────────


def _drop_manifest_file_entry(bundle_dir, rel_path: str) -> None:
    """Delete a data file AND drop its manifest.files entry — so validate() no longer checksums it,
    it streams as empty, yet manifest.counts still claims its rows (the silent-empty-success bug)."""
    manifest_path = bundle_dir / "manifest.json"
    data = json.loads(manifest_path.read_text("utf-8"))
    data["files"] = [entry for entry in data["files"] if entry["path"] != rel_path]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    (bundle_dir / rel_path).unlink()


async def test_import_fails_when_manifest_declares_a_missing_data_file(
    export_facade, tmp_path
) -> None:
    """A bundle whose manifest declares points it no longer carries must FAIL loudly at
    reconciliation (naming the domain) and roll back — never a false success with phantom counts."""
    exporter = CollectionExporter(
        export_facade, docforge_version="test", created_at="2026-01-01T00:00:00+00:00"
    )
    await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    # points.jsonl vanishes from the checked files but counts.points still says 1.
    _drop_manifest_file_entry(tmp_path / "bundle", "qdrant/points.jsonl")
    reader = BundleReader(tmp_path / "bundle")
    reader.validate()  # passes: the dropped file is no longer listed, so it is never checksummed
    facade = FakeImportFacade()

    with pytest.raises(CollectionImportError) as exc:
        await CollectionImporterV1(facade, reader).run()

    assert "reconciliation failed" in str(exc.value)
    assert "points" in str(exc.value)
    # The half-built collection was rolled back — no phantom-count success left behind.
    assert facade.created is not None
    assert facade.rolled_back == [facade.created.id]


# ─────────────────────── Item 2 — consistent dangling-reference handling ───────────────────────


def _block_data(block_id: str, document_id: str, *, parent_id: str | None) -> dict:
    """A minimal ir_blocks bundle row for the pure deserializer tests."""
    return {
        "id": block_id,
        "document_id": document_id,
        "block_type": "text",
        "page": 0,
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "reading_order": 0,
        "column_index": 0,
        "parent_id": parent_id,
        "level": None,
        "text": "x",
        "is_boilerplate": False,
        "language": "en",
        "confidence": None,
    }


def _ctx_with_one_doc() -> tuple[RemapContext, str, uuid.UUID]:
    """A RemapContext mapping the fixture document to a fresh uuid (blocks left to the caller)."""
    old_doc = str(DOC_ID)
    new_doc = uuid.uuid4()
    ctx = RemapContext(field_ids={})
    ctx.documents = {old_doc: new_doc}
    return ctx, old_doc, new_doc


def test_deserialize_remaps_parent_child_block_chain_consistently() -> None:
    """A parent→child block chain: the child's parent_id resolves to the parent's REMAPPED id, and
    both re-namespace onto the new document id (the deep-chain case the happy path never exercised)."""
    ctx, old_doc, new_doc = _ctx_with_one_doc()
    parent_old = f"{old_doc}:#/texts/0"
    child_old = f"{old_doc}:#/texts/1"
    ctx.blocks = {
        parent_old: ctx.remap_block_id(parent_old, old_doc),
        child_old: ctx.remap_block_id(child_old, old_doc),
    }

    parent = RowDeserializer.block(_block_data(parent_old, old_doc, parent_id=None), ctx)
    child = RowDeserializer.block(_block_data(child_old, old_doc, parent_id=parent_old), ctx)

    assert parent.parent_id is None
    assert child.parent_id == parent.id
    assert parent.id.startswith(f"{new_doc}:") and child.id.startswith(f"{new_doc}:")


def test_deserialize_drops_dangling_block_parent(monkeypatch) -> None:
    """A block whose parent is absent from the bundle degrades to a NULL parent (recoverable) AND
    logs a warning naming the id — never a silent drop, never a loud fail."""
    ctx, old_doc, _new = _ctx_with_one_doc()
    child_old = f"{old_doc}:#/texts/1"
    ctx.blocks = {child_old: ctx.remap_block_id(child_old, old_doc)}  # parent NOT mapped
    warnings: list[str] = []
    monkeypatch.setattr(
        RowDeserializer, "logger", SimpleNamespace(warning=lambda msg: warnings.append(msg))
    )

    block = RowDeserializer.block(
        _block_data(child_old, old_doc, parent_id=f"{old_doc}:#/texts/0"), ctx
    )

    assert block.parent_id is None  # dropped, not a KeyError, not a stale foreign id
    assert warnings and "block parent" in warnings[0]


def test_deserialize_drops_dangling_figure_caption(monkeypatch) -> None:
    """A figure caption pointing at an absent block degrades to NULL + a logged warning."""
    ctx, old_doc, _new = _ctx_with_one_doc()
    fig_block_old = f"{old_doc}:#/pictures/0"
    ctx.blocks = {fig_block_old: ctx.remap_block_id(fig_block_old, old_doc)}  # caption NOT mapped
    warnings: list[str] = []
    monkeypatch.setattr(
        RowDeserializer, "logger", SimpleNamespace(warning=lambda msg: warnings.append(msg))
    )

    figure = RowDeserializer.block_figure(
        {
            "block_id": fig_block_old,
            "crop_blob_hash": None,
            "caption_block_id": f"{old_doc}:#/texts/9",
        },
        ctx,
    )

    assert figure.caption_block_id is None
    assert warnings and "figure caption" in warnings[0]


def test_deserialize_skips_unknown_metadata_field(monkeypatch) -> None:
    """A metadata value whose field is absent from the restored schema is SKIPPED (None) + logged —
    both scopes behave identically (the consistency the item asks for)."""
    ctx, old_doc, _new = _ctx_with_one_doc()
    ctx.field_ids = {"author": 100}  # 'topic' deliberately absent
    ctx.chunks = {str(CHUNK_ID): uuid.uuid4()}
    warnings: list[str] = []
    monkeypatch.setattr(
        RowDeserializer, "logger", SimpleNamespace(warning=lambda msg: warnings.append(msg))
    )

    doc_meta = RowDeserializer.document_metadata(
        {"document_id": old_doc, "field_name": "topic", "value": "x", "origin": "user"}, ctx
    )
    chunk_meta = RowDeserializer.chunk_metadata(
        {"chunk_id": str(CHUNK_ID), "field_name": "topic", "value": "x", "origin": "generated"}, ctx
    )

    assert doc_meta is None and chunk_meta is None
    assert len(warnings) == 2
    assert all("topic" in message for message in warnings)


def test_to_point_drops_stale_document_id(monkeypatch) -> None:
    """A point whose payload document_id resolves to no restored document has that stale key DROPPED
    (not kept as a wrong foreign id) + a logged warning, while the point itself is still restored."""
    ctx = RemapContext(field_ids={})
    ctx.documents = {}  # the referenced doc is NOT in the bundle
    ctx.chunks = {str(CHUNK_ID): uuid.uuid4()}
    warnings: list[str] = []
    monkeypatch.setattr(
        CollectionImporterV1, "logger", SimpleNamespace(warning=lambda msg: warnings.append(msg))
    )
    record = {
        "id": str(CHUNK_ID),
        "vectors": {"content_dense": [0.1, 0.2, 0.3, 0.4]},
        "payload": {"document_id": str(DOC_ID), "enabled": True},
    }

    point = CollectionImporterV1._to_point(record, ctx)

    assert point is not None
    assert "document_id" not in point.payload  # dropped, not left stale
    assert point.payload["enabled"] is True  # the rest of the payload survives
    assert warnings and "document_id" in warnings[0]


# ─────────────────────── Item 4 — config_versions history is explicitly not restored ───────────────────────


class _HistoryExportFacade(FakeExportFacade):
    """A source collection carrying a redacted config-version history in collection.json."""

    async def list_config_versions(self, _collection_id):
        return [
            SimpleNamespace(version=1, config={}, note="creation", created_at=None),
            SimpleNamespace(version=2, config={}, note="tuned", created_at=None),
        ]


async def test_import_does_not_restore_config_version_history(tmp_path, monkeypatch) -> None:
    """DECISION: restoring historical version rows needs a store-facade write outside the transfer
    engine's scope, so the history is dropped ON PURPOSE. The import still succeeds (history is not
    required) and the drop is announced explicitly rather than silently."""
    reader = await _bundle(_HistoryExportFacade(), tmp_path)
    assert len(reader.read_collection().config_versions) == 2  # the bundle DID carry the history
    facade = FakeImportFacade()
    infos: list[str] = []
    monkeypatch.setattr(
        CollectionImporterV1, "logger", SimpleNamespace(info=lambda msg: infos.append(msg))
    )

    result = await CollectionImporterV1(facade, reader).run()

    # The import succeeded despite the carried history (it is not restored, not required).
    assert result.collection_id == facade.created.id
    # ...and the discard was announced, not silent.
    assert any("config history" in message for message in infos)


# ─────────────────────── Item 5 — zero-point + double-import ───────────────────────


class _NoPointExportFacade(FakeExportFacade):
    """A source collection with rows but NO vectors (never embedded / all points removed)."""

    async def scroll_points(self, _collection_id, _batch_size=256):
        return
        yield  # pragma: no cover — makes this an (empty) async generator


async def test_import_restores_a_zero_point_document(tmp_path) -> None:
    """A document with zero vectors imports cleanly: the vector space is never ensured, no point is
    upserted, and the manifest reconciliation (points 0 == 0) still passes."""
    reader = await _bundle(_NoPointExportFacade(), tmp_path)
    facade = FakeImportFacade()

    result = await CollectionImporterV1(facade, reader).run()

    assert facade.restored["Document"][0].collection_id == result.collection_id
    assert facade.points == []
    assert (
        facade.ensured_dense_dim is None
    )  # no vector space created when there is nothing to upsert
    assert result.counts["points"] == 0
    assert result.counts["documents"] == 1


async def test_import_double_import_yields_independent_collections(export_facade, tmp_path) -> None:
    """Importing the SAME bundle twice produces two INDEPENDENT collections: fresh collection ids and
    fresh entity ids each time, so nothing collides (the id-remap is per-import, not shared)."""
    reader = await _bundle(export_facade, tmp_path)
    facade_a = FakeImportFacade()
    facade_b = FakeImportFacade()

    result_a = await CollectionImporterV1(facade_a, reader).run()
    result_b = await CollectionImporterV1(facade_b, reader).run()

    assert result_a.collection_id != result_b.collection_id
    doc_a = facade_a.restored["Document"][0]
    doc_b = facade_b.restored["Document"][0]
    chunk_a = facade_a.restored["Chunk"][0]
    chunk_b = facade_b.restored["Chunk"][0]
    # Independent remap: the two imports share no id, and neither reuses the source ids.
    assert doc_a.id != doc_b.id and chunk_a.id != chunk_b.id
    assert doc_a.id != DOC_ID and doc_b.id != DOC_ID
    assert chunk_a.id != CHUNK_ID and chunk_b.id != CHUNK_ID
