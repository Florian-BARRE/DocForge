# ====== Code Summary ======
# CollectionExporter — lays out a `.dcexport` bundle tree in a working directory by STREAMING every
# source out of the store gateway: the collection contract + schema, then the documents one at a time
# (each document's whole row set read in one session and fanned into the per-table JSONL sinks), then
# the Qdrant points scrolled in bounded batches, then the deduped blob bytes (one file per unique
# hash). The blob set + the live chunk ids are derived FROM the same document snapshot the doc pass
# wrote (not a second live query), so the bundle only references what it actually saw; a referenced
# blob that vanished mid-export ABORTS loudly (a clear error naming the document) instead of producing
# a silently-lossy bundle. It never buffers a whole table or all blobs in memory. It writes the
# manifest LAST, with the accumulated per-file checksums and counts. Tar assembly + S3 upload are the
# task's job — this only produces the on-disk tree, so a crash leaves an unpublished working dir.

# ====== Standard Library Imports ======
from __future__ import annotations

import contextlib
import pathlib
import uuid
from collections.abc import Callable

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import redact_blob_secrets, redact_config_snapshot
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

        # 2. The documents + their IR/chunks, streamed a document at a time. Two by-products of the
        #    SAME snapshot are captured here so steps 3-4 stay self-consistent with the rows written:
        #    the live chunk ids (so the vector pass drops orphan points) and the blob hashes those very
        #    rows reference (so the blob pass exports exactly the blobs the bundle points at — never a
        #    live re-query that could disagree with the documents already written).
        counts, live_chunk_ids, blob_refs = await self._write_documents(writer, collection_id)

        # 3. The vectors (scrolled, orphan points filtered) and the blob bytes referenced BY the
        #    document snapshot (a missing referenced blob aborts the export loudly — never a silent drop).
        counts["points"] = await self._write_points(writer, collection_id, live_chunk_ids)
        counts["blobs"] = await self._write_blobs(writer, blob_refs)
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
        """Build collection.json from the collection row + its config history.

        Provider secrets (every provider node's ``api_key`` across the live ``pipeline`` and ``search``
        blobs AND every archived ``config_versions[].config`` snapshot) are REDACTED here — the same
        masking every outbound collection GET applies — so a portable bundle never carries live keys
        off the server. A READ-scoped key can export→download a collection; the mask (last 4 chars,
        non-reversible) is all it ever sees. On import the redacted placeholder restores as a plain
        string, so the operator re-enters each provider key on the new server.
        """
        versions = await self._facade.list_config_versions(collection.id)
        return CollectionContractModel(
            name=collection.name,
            supported_formats=list(collection.supported_formats),
            max_file_size_bytes=collection.max_file_size_bytes,
            job_timeout_seconds=collection.job_timeout_seconds,
            needs_reindex=collection.needs_reindex,
            pipeline=redact_blob_secrets(collection.pipeline) or {},
            search=redact_blob_secrets(collection.search) or {},
            config_versions=[
                ConfigVersionModel(
                    version=version.version,
                    config=redact_config_snapshot(version.config),
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

    async def _write_documents(
        self, writer, collection_id: uuid.UUID
    ) -> tuple[dict[str, int], set[str], dict[str, str]]:
        """Stream every document's row set into the sinks.

        Returns the manifest counts, the set of live chunk ids (for the orphan-point filter) and a
        ``blob_hash → referencing-document label`` map derived from the SAME rows just written, so the
        blob pass exports exactly what the bundle references (self-consistent snapshot) and can name
        the offending document when a referenced blob has vanished.
        """
        document_ids = await self._facade.list_document_ids(collection_id)
        total = len(document_ids)
        live_chunk_ids: set[str] = set()
        blob_refs: dict[str, str] = {}
        with contextlib.ExitStack() as stack:
            sinks = {
                key: stack.enter_context(writer.sink(path)) for key, path in _DOCUMENT_SINKS.items()
            }
            for index, document_id in enumerate(document_ids):
                rows = await self._facade.read_document_export(document_id)
                self._fan_out(sinks, rows, live_chunk_ids, blob_refs)
                if total:
                    self._progress("documents", 5 + int(70 * (index + 1) / total))
            counts = {field: sinks[key].rows for key, field in _COUNTED_SINKS.items()}
            return counts, live_chunk_ids, blob_refs

    @staticmethod
    def _fan_out(sinks: dict, rows, live_chunk_ids: set[str], blob_refs: dict[str, str]) -> None:
        """Serialize one document's rows into the sinks, recording live chunk ids + referenced blobs."""
        # Record every blob hash THESE rows reference (document source/pdf, page renders, figure crops),
        # keyed to a human label so a later missing-blob abort can name the document. Mirrors exactly
        # what BlobApi.collect_hashes_for_collection unions — but scoped to the snapshot being written.
        label = rows.document.filename or str(rows.document.id)
        for blob_hash in (rows.document.source_hash, rows.document.pdf_blob_hash):
            if blob_hash:
                blob_refs.setdefault(blob_hash, label)
        for page in rows.pages:
            if page.render_blob_hash:
                blob_refs.setdefault(page.render_blob_hash, label)
        for figure in rows.figures:
            if figure.crop_blob_hash:
                blob_refs.setdefault(figure.crop_blob_hash, label)

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
            live_chunk_ids.add(str(chunk.id))
        for link in rows.composition:
            sinks["chunk_blocks"].write(RowSerializer.chunk_block(link))
        for chunk_id, name, value, origin in rows.chunk_metadata:
            sinks["chunk_metadata"].write(
                RowSerializer.chunk_metadata(chunk_id, name, value, origin)
            )
        for entity in rows.entities:
            sinks["entity_mentions"].write(RowSerializer.entity_mention(entity))

    async def _write_points(
        self, writer, collection_id: uuid.UUID, live_chunk_ids: set[str]
    ) -> int:
        """Scroll Qdrant points into points.jsonl, DROPPING orphans; return the emitted count.

        A point whose id has no live chunk row in the bundle (``point.id == chunk.id``) is an orphan
        the importer would discard anyway — skipping it here keeps ``counts.points`` equal to the
        vector count the import actually restores, so source vs imported never appears to lose points.
        """
        with writer.sink(BundlePaths.POINTS) as sink:
            async for record in self._facade.scroll_points(collection_id, self._scroll_batch):
                row = RowSerializer.point(record)
                if row["id"] not in live_chunk_ids:
                    continue
                sink.write(row)
            self._progress("vectors", 85)
            return sink.rows

    async def _write_blobs(self, writer, blob_refs: dict[str, str]) -> int:
        """Write the registry rows + the deduped bytes for the SNAPSHOT-referenced hashes; return count.

        The hash set comes from the document rows just written (``blob_refs``), NOT a fresh live query,
        so the bundle only ever references blobs the doc pass actually saw. A referenced blob whose
        registry row or S3 object has vanished (a concurrent delete/reingest) ABORTS the export with a
        clear error naming the document — a corrupt, silently-lossy bundle is never produced.
        """
        hashes = list(blob_refs)
        blob_rows = await self._facade.get_blob_rows(hashes)
        # A referenced hash with no registry row = a concurrent delete raced the doc pass. Fail loud.
        present = {row.content_hash for row in blob_rows}
        missing_rows = [blob_hash for blob_hash in hashes if blob_hash not in present]
        if missing_rows:
            blob_hash = missing_rows[0]
            raise CollectionExportError(
                f"blob {blob_hash} referenced by document '{blob_refs[blob_hash]}' has no registry "
                f"row (a concurrent delete/reingest removed it mid-export) — aborting rather than "
                f"writing a corrupt bundle"
            )
        with writer.sink(BundlePaths.BLOBS) as sink:
            for row in blob_rows:
                sink.write(RowSerializer.blob(row))
                try:
                    data = await self._facade.read_blob_bytes(row.s3_key)
                except Exception as exc:
                    raise CollectionExportError(
                        f"blob {row.content_hash} referenced by document "
                        f"'{blob_refs.get(row.content_hash, row.content_hash)}' is missing from "
                        f"object storage ({exc}) — aborting rather than writing a corrupt bundle"
                    ) from exc
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
