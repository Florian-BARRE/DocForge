# ====== Code Summary ======
# CollectionImporterV1 — the "translator in reverse" for a v1 bundle: it creates a BRAND-NEW
# collection (fresh UUID; the name is renamed on collision, never an overwrite), builds a RemapContext
# (fresh ids for every entity), then STAGES the restore in FK order — blobs first (documents/pages/
# figures reference them), then the catalogue, metadata (field id remapped by name), pages, the IR,
# the chunks, and finally the Qdrant vectors. Blob bytes are STREAMED in a bounded byte-budget batch
# (never the whole bundle resident at once), mirroring the exporter's one-blob-at-a-time shape. Every
# id is REGENERATED and every foreign key rewritten
# consistently, so a bundle restores anywhere — including back onto its origin server (id preservation
# would collide on the global primary keys). The chunk's new UUID is reused as its Qdrant point id, so
# chunk.id == point.id still holds. Any failure ROLLS BACK the whole new collection (Qdrant drop → PG
# cascade → orphan-only blob purge), leaving pre-existing collections and shared blobs untouched. A
# tiny importer registry keyed on format_version is the seam a future V2 migrator slots into.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import CollectionTransferFacade
from shared_libs.services.db.postgresql.tables import Blob, Collection
from shared_libs.services.db.qdrant import QdrantPoint, SparseVec
from shared_libs.services.db.s3 import S3Object

# ====== Local Project Imports ======
from ..bundle import BundleReader
from ..manifest import CollectionContractModel, is_supported_version
from ..paths import BundlePaths
from .remap import RemapBuilder, RemapContext
from .rows import RowDeserializer

ProgressFn = Callable[[str, int], None]


@dataclass(slots=True)
class ImportResult:
    """The outcome of a successful import — the new collection and its restored counts."""

    collection_id: uuid.UUID
    collection_name: str
    counts: dict[str, int]


class CollectionImportError(Exception):
    """Raised when a bundle cannot be imported (unsupported version, missing data, restore failure)."""


class CollectionImporterV1:
    """Restores a v1 `.dcexport` bundle as a NEW collection (id-remapped, transactional rollback)."""

    logger = loggerplusplus.bind(identifier="CollectionImporterV1")

    def __init__(
        self,
        facade: CollectionTransferFacade,
        reader: BundleReader,
        *,
        progress: ProgressFn | None = None,
        point_batch: int = 500,
        blob_batch_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        """
        Args:
            facade (CollectionTransferFacade): The store gateway (id-remapped restore writes).
            reader (BundleReader): The validated bundle reader (call ``validate`` first).
            progress (ProgressFn | None): Optional ``(stage, percent)`` callback.
            point_batch (int): How many points to accumulate before an upsert (bounds memory).
            blob_batch_bytes (int): Byte budget for the blob restore — accumulate blob bytes only up
                to this many, then flush to S3 and release. Bounds peak resident memory to roughly one
                batch (mirroring the exporter's one-blob-at-a-time streaming), NOT the whole bundle.
        """
        self._facade = facade
        self._reader = reader
        self._progress = progress or (lambda _stage, _pct: None)
        self._point_batch = point_batch
        self._blob_batch_bytes = blob_batch_bytes

    async def run(self, target_name: str | None = None) -> ImportResult:
        """
        Import the bundle as a new collection.

        Args:
            target_name (str | None): A caller-chosen name; falls back to the bundle's name. Either
                way a collision is resolved by appending a suffix (never an overwrite).

        Returns:
            ImportResult: The new collection id/name and the restored row counts.
        """
        manifest = self._reader.manifest
        contract = self._reader.read_collection()
        name = await self._resolve_name(target_name or contract.name)

        # Everything from the collection create onward runs under ONE rollback guard: a failure at any
        # step — create, the id-remap build, or the staged restore — deletes the half-built collection,
        # so not even an empty collection + schema is ever left behind (the feature's headline promise).
        created = None
        try:
            # 1. Create the new collection + schema (fresh id + fresh autoincrement field ids).
            fields = [
                RowDeserializer.metadata_field(row)
                for row in self._reader.iter_rows(BundlePaths.METADATA_FIELDS)
            ]
            created = await self._facade.create_collection(
                self._collection_row(contract, name), fields
            )
            self._progress("collection", 5)

            # 2. Build the id-remap plan (fresh ids for every entity) from the created schema + bundle.
            field_ids = await self._facade.field_id_map(created.id)
            ctx = RemapBuilder.build(self._reader, field_ids)

            # 3. Staged restore.
            await self._restore(created.id, ctx, manifest.dense_dim)
        except Exception as exc:
            if created is not None:
                self.logger.exception(
                    f"Import failed for new collection {created.id}; rolling back"
                )
                await self._facade.rollback_collection(created.id)
            raise CollectionImportError(f"import failed and was rolled back: {exc}") from exc

        self._progress("done", 100)
        counts = manifest.counts.model_dump()
        self.logger.info(f"Imported bundle into new collection {created.id} ('{name}')")
        return ImportResult(collection_id=created.id, collection_name=name, counts=counts)

    async def _resolve_name(self, desired: str) -> str:
        """Return ``desired`` if free, else append an ' (imported[ N])' suffix until it is unique."""
        if not await self._facade.name_taken(desired):
            return desired
        candidate = f"{desired} (imported)"
        counter = 2
        while await self._facade.name_taken(candidate):
            candidate = f"{desired} (imported {counter})"
            counter += 1
        return candidate

    @staticmethod
    def _collection_row(contract: CollectionContractModel, name: str) -> Collection:
        """Build the new Collection row from the bundle contract (fresh id assigned by the DB)."""
        return Collection(
            name=name,
            supported_formats=list(contract.supported_formats),
            max_file_size_bytes=contract.max_file_size_bytes,
            job_timeout_seconds=contract.job_timeout_seconds,
            needs_reindex=contract.needs_reindex,
            pipeline=contract.pipeline,
            search=contract.search,
        )

    async def _restore(self, collection_id: uuid.UUID, ctx: RemapContext, dense_dim: int) -> None:
        """Stage the whole restore in FK order (blobs first, vectors last), remapping every id."""
        # 1. Blobs BEFORE any row that references them (document/page/figure blob FKs are not deferred).
        await self._restore_blobs()
        self._progress("blobs", 20)

        # 2. The catalogue + document-scope metadata + pages.
        await self._restore_table(
            BundlePaths.DOCUMENTS, ctx, lambda d, c: RowDeserializer.document(d, collection_id, c)
        )
        await self._restore_metadata(BundlePaths.DOCUMENT_METADATA, ctx, chunk_scope=False)
        await self._restore_table(BundlePaths.PAGES, ctx, RowDeserializer.page)
        self._progress("documents", 40)

        # 3. The IR — blocks, then their details, then enrichments + attempts (each a full-table tx).
        await self._restore_table(BundlePaths.IR_BLOCKS, ctx, RowDeserializer.block)
        await self._restore_table(BundlePaths.IR_TABLES, ctx, RowDeserializer.block_table)
        await self._restore_table(BundlePaths.IR_FIGURES, ctx, RowDeserializer.block_figure)
        await self._restore_table(BundlePaths.IR_ENRICHMENTS, ctx, RowDeserializer.block_enrichment)
        await self._restore_table(
            BundlePaths.IR_ENRICHMENT_ATTEMPTS, ctx, RowDeserializer.enrichment_attempt
        )
        self._progress("ir", 60)

        # 4. The chunks, their composition, generated metadata, entities.
        await self._restore_table(BundlePaths.CHUNKS, ctx, RowDeserializer.chunk)
        await self._restore_table(BundlePaths.CHUNK_BLOCKS, ctx, RowDeserializer.chunk_block)
        await self._restore_metadata(BundlePaths.CHUNK_METADATA, ctx, chunk_scope=True)
        await self._restore_table(BundlePaths.ENTITY_MENTIONS, ctx, RowDeserializer.entity_mention)
        self._progress("chunks", 80)

        # 5. The vectors — the point id is the chunk's NEW id (kept == chunk.id), and its payload
        #    document_id is remapped too, so search resolves back to the restored rows.
        await self._restore_points(collection_id, ctx, dense_dim)
        self._progress("vectors", 98)

    async def _restore_blobs(self) -> None:
        """Register the blob rows + upload their content-verified bytes, STREAMED in bounded batches.

        The bundle can carry up to IMPORT_MAX_BUNDLE_BYTES of blob bytes; reading them all into memory
        before a single store would make the whole bundle resident at once. Instead this accumulates
        blob bytes only up to ``_blob_batch_bytes`` (one blob always fits, however large), flushes that
        batch to S3 + the registry, releases it, and continues — so peak resident memory is bounded by
        one batch, mirroring the exporter's one-blob-at-a-time streaming. Each ``store_blobs`` is
        idempotent (dedup by content hash) and a partial-then-failed import is cleaned by the rollback.
        """
        objects: list[S3Object] = []
        rows: list[Blob] = []
        pending_bytes = 0
        for data in self._reader.iter_rows(BundlePaths.BLOBS):
            blob = RowDeserializer.blob(data)

            # Content-addressing invariant: a blob's storage key IS its content hash (see the upload
            # and cache paths). NEVER trust the bundle's own s3_key — a tampered bundle can set it to
            # a VICTIM object's key while carrying attacker bytes, and read_blob only verifies the
            # content_hash, not the key, so the put would overwrite that victim object. Pin both the
            # uploaded object key and the registered row to the content hash: an import can then only
            # ever write to its own content address. A legitimate bundle already has them equal.
            if blob.s3_key != blob.content_hash:
                self.logger.warning(
                    f"Bundle blob s3_key '{blob.s3_key}' != content_hash '{blob.content_hash}' — "
                    f"pinning to the content hash (content-addressing invariant)."
                )
                blob.s3_key = blob.content_hash

            content = self._reader.read_blob(blob.content_hash)
            rows.append(blob)
            objects.append(
                S3Object(key=blob.content_hash, data=content, content_type=blob.mime_type)
            )
            pending_bytes += len(content)

            # Flush once the byte budget is reached, then release the batch so it can be reclaimed.
            if pending_bytes >= self._blob_batch_bytes:
                await self._facade.store_blobs(objects, rows)
                objects, rows, pending_bytes = [], [], 0

        if objects:
            await self._facade.store_blobs(objects, rows)

    async def _restore_table(
        self, path: str, ctx: RemapContext, deserialize: Callable[[dict, RemapContext], Any]
    ) -> None:
        """Stream one table file, deserialize+remap every row, and insert it in ONE transaction."""
        rows = [deserialize(data, ctx) for data in self._reader.iter_rows(path)]
        await self._facade.restore_rows(rows)

    async def _restore_metadata(self, path: str, ctx: RemapContext, *, chunk_scope: bool) -> None:
        """Restore metadata rows, remapping the owner id + field_name → new field id (dropping unknown)."""
        rows = []
        for data in self._reader.iter_rows(path):
            row = (
                RowDeserializer.chunk_metadata(data, ctx)
                if chunk_scope
                else RowDeserializer.document_metadata(data, ctx)
            )
            if row is not None:
                rows.append(row)
        await self._facade.restore_rows(rows)

    async def _restore_points(
        self, collection_id: uuid.UUID, ctx: RemapContext, dense_dim: int
    ) -> None:
        """Ensure the vector space and upsert every point under its REMAPPED id, in bounded batches."""
        batch: list[QdrantPoint] = []
        ensured = False
        for record in self._reader.iter_rows(BundlePaths.POINTS):
            point = self._to_point(record, ctx)
            if point is None:
                continue
            if not ensured:
                await self._facade.ensure_vector_space(collection_id, dense_dim)
                ensured = True
            batch.append(point)
            if len(batch) >= self._point_batch:
                await self._facade.upsert_points(collection_id, batch)
                batch = []
        if batch:
            await self._facade.upsert_points(collection_id, batch)

    @staticmethod
    def _to_point(record: dict[str, Any], ctx: RemapContext) -> QdrantPoint | None:
        """
        Rebuild a QdrantPoint under REMAPPED ids: point id = the chunk's new UUID (so it still equals
        chunk.id), and the payload document_id is remapped too. A point whose chunk is unknown (an
        orphan not in the chunk map) is skipped. Dense (list) vs sparse ({...}) vectors are split.
        """
        new_chunk_id = ctx.chunks.get(record["id"])
        if new_chunk_id is None:
            return None
        dense: dict[str, list[float]] = {}
        sparse: dict[str, SparseVec] = {}
        for name, vector in (record.get("vectors") or {}).items():
            if isinstance(vector, dict):
                sparse[name] = SparseVec(indices=vector["indices"], values=vector["values"])
            else:
                dense[name] = list(vector)
        payload = dict(record.get("payload") or {})
        old_document_id = payload.get("document_id")
        if old_document_id in ctx.documents:
            payload["document_id"] = str(ctx.documents[old_document_id])
        return QdrantPoint(point_id=str(new_chunk_id), payload=payload, dense=dense, sparse=sparse)


# The importer registry — format_version → the class that reads it. A V2 adds its entry + migrator.
_IMPORTERS: dict[int, type[CollectionImporterV1]] = {1: CollectionImporterV1}


def get_importer(
    format_version: int,
    facade: CollectionTransferFacade,
    reader: BundleReader,
    *,
    progress: ProgressFn | None = None,
) -> CollectionImporterV1:
    """
    Resolve the importer for a bundle's format version (the version-dispatch seam).

    Args:
        format_version (int): The manifest's format version.
        facade (CollectionTransferFacade): The store gateway.
        reader (BundleReader): The validated bundle reader.
        progress (ProgressFn | None): Optional progress callback.

    Returns:
        CollectionImporterV1: The importer that can read this version.

    Raises:
        CollectionImportError: When no importer is registered for the version.
    """
    if not is_supported_version(format_version) or format_version not in _IMPORTERS:
        raise CollectionImportError(f"no importer for bundle format_version {format_version}")
    return _IMPORTERS[format_version](facade, reader, progress=progress)


__all__ = [
    "CollectionImporterV1",
    "CollectionImportError",
    "ImportResult",
    "get_importer",
]
