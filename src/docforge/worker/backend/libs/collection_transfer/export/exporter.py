# ====== Code Summary ======
# CollectionExporter — lays out a `.dcexport` bundle tree in a working directory by STREAMING every
# source out of the store gateway: the collection contract + schema, then the documents one at a time
# (each document's whole row set read in one session and fanned into the per-table JSONL sinks), then
# the Qdrant points scrolled in bounded batches, then the deduped blob bytes (one file per unique
# hash). It never buffers a whole table or all blobs in memory. It writes the manifest LAST, with the
# accumulated per-file checksums and counts. Tar assembly + S3 upload are the task's job — this only
# produces the on-disk tree, so a crash leaves an unpublished working dir, never a partial artifact.

# ====== Standard Library Imports ======
from __future__ import annotations

import contextlib
import pathlib
import uuid
from collections.abc import Callable

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import CollectionTransferFacade
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ..bundle import BundleWriter
from ..manifest import (
    CURRENT_FORMAT_VERSION,
    CollectionContractModel,
    CollectionRef,
    ConfigVersionModel,
    ExportManifest,
    TransferCounts,
)
from ..paths import BundlePaths
from .rows import RowSerializer

ProgressFn = Callable[[str, int], None]


class CollectionExportError(Exception):
    """Raised when a collection cannot be exported (e.g. it no longer exists)."""


class CollectionExporter:
    """Streams a collection's whole material into a `.dcexport` working-directory tree."""

    def __init__(
        self,
        facade: CollectionTransferFacade,
        *,
        docforge_version: str,
        created_at: str,
        compression: str = "none",
        progress: ProgressFn | None = None,
        scroll_batch: int = 256,
    ) -> None:
        """
        Args:
            facade (CollectionTransferFacade): The store gateway (streamed reads).
            docforge_version (str): The producing build's version (manifest provenance).
            created_at (str): ISO-8601 assembly timestamp (passed in for determinism-friendliness).
            compression (str): ``"none"`` or ``"zstd"`` — recorded in the manifest for the archiver.
            progress (ProgressFn | None): Optional ``(stage, percent)`` callback.
            scroll_batch (int): Qdrant scroll page size.
        """
        self._facade = facade
        self._docforge_version = docforge_version
        self._created_at = created_at
        self._compression = compression
        self._progress = progress or (lambda _stage, _pct: None)
        self._scroll_batch = scroll_batch

    async def build(self, collection_id: uuid.UUID, work_dir: pathlib.Path) -> ExportManifest:
        """
        Assemble the bundle tree for ``collection_id`` under ``work_dir`` and return its manifest.

        Args:
            collection_id (uuid.UUID): The collection to export.
            work_dir (pathlib.Path): An empty working directory to lay the tree into.

        Returns:
            ExportManifest: The written manifest (also persisted as manifest.json in the tree).
        """
        # 1. The contract + schema — fail fast if the collection vanished.
        collection = await self._facade.get_collection(collection_id)
        if collection is None:
            raise CollectionExportError(f"collection {collection_id} not found")
        schema = await self._facade.get_schema(collection_id)
        dense_dim = await self._facade.dense_dim(collection_id)
        writer = BundleWriter(work_dir)
        self._progress("contract", 2)
        writer.write_collection(await self._contract(collection))
        fields_written = self._write_schema(writer, schema)

        # 2. The documents + their IR/chunks, streamed a document at a time.
        counts = await self._write_documents(writer, collection_id)

        # 3. The vectors (scrolled) and the deduped blob bytes.
        counts["points"] = await self._write_points(writer, collection_id)
        counts["blobs"] = await self._write_blobs(writer, collection_id)
        counts["metadata_fields"] = fields_written

        # 4. The manifest LAST, with every accumulated checksum + count.
        manifest = ExportManifest(
            format_version=CURRENT_FORMAT_VERSION,
            docforge_version=self._docforge_version,
            created_at=self._created_at,
            collection=CollectionRef(id=str(collection.id), name=collection.name),
            dense_dim=dense_dim,
            compression=self._compression,
            counts=TransferCounts(**counts),
        )
        writer.write_manifest(manifest)
        self._progress("manifest", 100)
        return manifest

    async def _contract(self, collection: Collection) -> CollectionContractModel:
        """Build collection.json from the collection row + its config history."""
        versions = await self._facade.list_config_versions(collection.id)
        return CollectionContractModel(
            name=collection.name,
            supported_formats=list(collection.supported_formats),
            max_file_size_bytes=collection.max_file_size_bytes,
            job_timeout_seconds=collection.job_timeout_seconds,
            needs_reindex=collection.needs_reindex,
            pipeline=collection.pipeline or {},
            search=collection.search or {},
            config_versions=[
                ConfigVersionModel(
                    version=version.version,
                    config=version.config,
                    note=version.note,
                    created_at=version.created_at.isoformat() if version.created_at else None,
                )
                for version in reversed(versions)  # oldest → newest
            ],
        )

    def _write_schema(self, writer, schema) -> int:
        """Write the metadata schema JSONL; return how many fields were written."""
        with writer.sink(BundlePaths.METADATA_FIELDS) as sink:
            for row in schema:
                sink.write(RowSerializer.metadata_field(row))
            return sink.rows

    async def _write_documents(self, writer, collection_id: uuid.UUID) -> dict[str, int]:
        """Stream every document's row set into the per-table sinks; return the row counts."""
        document_ids = await self._facade.list_document_ids(collection_id)
        total = len(document_ids)
        with contextlib.ExitStack() as stack:
            sinks = {
                key: stack.enter_context(writer.sink(path)) for key, path in _DOCUMENT_SINKS.items()
            }
            for index, document_id in enumerate(document_ids):
                rows = await self._facade.read_document_export(document_id)
                self._fan_out(sinks, rows)
                if total:
                    self._progress("documents", 5 + int(70 * (index + 1) / total))
            return {field: sinks[key].rows for key, field in _COUNTED_SINKS.items()}

    @staticmethod
    def _fan_out(sinks: dict, rows) -> None:
        """Serialize one document's rows into the matching sinks."""
        sinks["documents"].write(RowSerializer.document(rows.document))
        for name, value, origin in rows.metadata:
            sinks["document_metadata"].write(
                RowSerializer.document_metadata(rows.document.id, name, value, origin)
            )
        for page in rows.pages:
            sinks["pages"].write(RowSerializer.page(page))
        for block in rows.blocks:
            sinks["ir_blocks"].write(RowSerializer.block(block))
        for table in rows.tables:
            sinks["ir_tables"].write(RowSerializer.block_table(table))
        for figure in rows.figures:
            sinks["ir_figures"].write(RowSerializer.block_figure(figure))
        for enrichment in rows.enrichments:
            sinks["ir_enrichments"].write(RowSerializer.block_enrichment(enrichment))
        for attempt in rows.attempts:
            sinks["ir_enrichment_attempts"].write(RowSerializer.enrichment_attempt(attempt))
        for chunk in rows.chunks:
            sinks["chunks"].write(RowSerializer.chunk(chunk))
        for link in rows.composition:
            sinks["chunk_blocks"].write(RowSerializer.chunk_block(link))
        for chunk_id, name, value, origin in rows.chunk_metadata:
            sinks["chunk_metadata"].write(
                RowSerializer.chunk_metadata(chunk_id, name, value, origin)
            )
        for entity in rows.entities:
            sinks["entity_mentions"].write(RowSerializer.entity_mention(entity))

    async def _write_points(self, writer, collection_id: uuid.UUID) -> int:
        """Scroll every Qdrant point into points.jsonl; return the point count."""
        with writer.sink(BundlePaths.POINTS) as sink:
            async for record in self._facade.scroll_points(collection_id, self._scroll_batch):
                sink.write(RowSerializer.point(record))
            self._progress("vectors", 85)
            return sink.rows

    async def _write_blobs(self, writer, collection_id: uuid.UUID) -> int:
        """Write the registry rows + the deduped bytes (one file per unique hash); return count."""
        hashes = await self._facade.collect_blob_hashes(collection_id)
        blob_rows = await self._facade.get_blob_rows(hashes)
        with writer.sink(BundlePaths.BLOBS) as sink:
            for row in blob_rows:
                sink.write(RowSerializer.blob(row))
                data = await self._facade.read_blob_bytes(row.s3_key)
                writer.write_blob(row.content_hash, data)
        self._progress("blobs", 98)
        return writer.blob_count


# Which document-scope sinks are opened together for the streamed fan-out.
_DOCUMENT_SINKS = {
    "documents": BundlePaths.DOCUMENTS,
    "document_metadata": BundlePaths.DOCUMENT_METADATA,
    "pages": BundlePaths.PAGES,
    "ir_blocks": BundlePaths.IR_BLOCKS,
    "ir_tables": BundlePaths.IR_TABLES,
    "ir_figures": BundlePaths.IR_FIGURES,
    "ir_enrichments": BundlePaths.IR_ENRICHMENTS,
    "ir_enrichment_attempts": BundlePaths.IR_ENRICHMENT_ATTEMPTS,
    "chunks": BundlePaths.CHUNKS,
    "chunk_blocks": BundlePaths.CHUNK_BLOCKS,
    "chunk_metadata": BundlePaths.CHUNK_METADATA,
    "entity_mentions": BundlePaths.ENTITY_MENTIONS,
}

# The counts surfaced in the manifest: sink key → the TransferCounts field it feeds.
_COUNTED_SINKS = {
    "documents": "documents",
    "pages": "pages",
    "ir_blocks": "blocks",
    "ir_enrichments": "enrichments",
    "chunks": "chunks",
    "entity_mentions": "entity_mentions",
}


__all__ = ["CollectionExporter", "CollectionExportError"]
