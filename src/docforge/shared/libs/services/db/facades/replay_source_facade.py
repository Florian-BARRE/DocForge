# ====== Code Summary ======
# ReplaySourceFacade — the READ side of a replay-from-stage run: rebuilds a document's persisted state
# as pipeline artefacts, so the worker can seed a mid-graph run without re-parsing. ``load_ir`` folds
# the stored block/table/figure/enrichment rows back into the canonical DocumentIR (pipeline-scope ids,
# optionally with the figure crops rehydrated from the object store); ``load_chunks`` rebuilds the stored
# final chunks (contextualized text, composition, generated metadata); ``load_document_meta`` returns
# the generated document-scope values; ``load_ingest_facts`` the intake facts. Read-only.

# ====== Standard Library Imports ======
import uuid
from collections import defaultdict

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import (
    Chunk,
    ChunkRole,
    DocumentIR,
    FieldOrigin,
    GeneratedDocumentMeta,
    IntakeResult,
)
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, DocumentApi, IRApi
from shared_libs.services.db.postgresql.tables import Document
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .ir_bundle_adapter import IRBundleAdapter
from .payloads import IRBundle


class ReplaySourceFacade(LoggerClass):
    """Rebuild a document's persisted IR / chunks / generated metadata as pipeline artefacts."""

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

    async def __attach_crops(
        self, document_id: uuid.UUID, ir: DocumentIR, bundle: IRBundle
    ) -> None:
        """Rehydrate every figure's crop bytes from the object store (key = content hash)."""
        prefix = f"{document_id}:"
        hashes = {
            row.block_id.removeprefix(prefix): row.crop_blob_hash
            for row in bundle.figures
            if row.crop_blob_hash
        }
        if not hashes:
            return
        async with self._s3.client() as client:
            for block in ir.blocks:
                key = hashes.get(block.id)
                if block.figure is not None and key:
                    block.figure.crop = await S3ObjectApi.get(client, self._s3.bucket, key)

    async def load_ir(
        self, document_id: uuid.UUID, *, with_crops: bool = False
    ) -> DocumentIR | None:
        """
        Rebuild the document's persisted (enriched) IR, in pipeline-scope ids.

        Args:
            document_id (uuid.UUID): The document.
            with_crops (bool): Rehydrate the figure crop bytes (needed only to re-run enrich).

        Returns:
            DocumentIR | None: The IR, or None when the document is unknown.
        """
        # 1. The document envelope + its stored IR rows, one session.
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                return None
            bundle = IRBundle(
                blocks=await IRApi.get_blocks(session, document_id),
                tables=await IRApi.get_tables(session, document_id),
                figures=await IRApi.get_figures(session, document_id),
                enrichments=await IRApi.get_document_enrichments(session, document_id),
            )
        # 2. Fold the rows into the canonical IR (pipeline ids), then the crops when asked.
        ir = IRBundleAdapter.to_document_ir(document, bundle, pipeline_ids=True)
        if with_crops:
            await self.__attach_crops(document_id, ir, bundle)
        return ir

    async def load_chunks(self, document_id: uuid.UUID) -> list[Chunk]:
        """
        Rebuild the document's stored FINAL chunks (the stored text is the contextualized form).

        The raw pre-contextualize text is not persisted, so ``text`` carries the stored (enriched)
        text and ``context`` is empty — ``enriched_text`` is therefore byte-identical to what was
        embedded. Block ids are pipeline-scope; pages derive from the composing blocks.

        Args:
            document_id (uuid.UUID): The document.

        Returns:
            list[Chunk]: The chunks in order, generated chunk metadata aboard.
        """
        prefix = f"{document_id}:"
        async with self._postgres.session() as session:
            rows = await ChunkApi.get_for_document(session, document_id)
            composition = await ChunkApi.get_composition_for_document(session, document_id)
            metadata = await ChunkApi.get_metadata_with_names_for_document(session, document_id)
            pages = {block.id: block.page for block in await IRApi.get_blocks(session, document_id)}
        blocks_of: dict[uuid.UUID, list[str]] = defaultdict(list)
        for member in composition:
            blocks_of[member.chunk_id].append(member.block_id)
        meta_of: dict[uuid.UUID, dict] = defaultdict(dict)
        for chunk_id, name, value, origin in metadata:
            if origin == FieldOrigin.GENERATED:
                meta_of[chunk_id][name] = value
        chunks: list[Chunk] = []
        for row in rows:
            block_ids = blocks_of.get(row.id, [])
            block_pages = [pages[b] for b in block_ids if pages.get(b) is not None] or [0]
            chunks.append(
                Chunk(
                    chunk_id=str(row.id),
                    ordinal=row.chunk_index,
                    text=row.text,
                    block_ids=[block_id.removeprefix(prefix) for block_id in block_ids],
                    token_count=row.token_count,
                    heading_path=list(row.heading_path or []),
                    role=ChunkRole(row.role),
                    page_start=min(block_pages),
                    page_end=max(block_pages),
                    generated_meta=meta_of.get(row.id, {}),
                )
            )
        return chunks

    async def load_document_meta(self, document_id: uuid.UUID) -> GeneratedDocumentMeta:
        """The document's stored GENERATED document-scope values."""
        async with self._postgres.session() as session:
            rows = await DocumentApi.get_metadata_with_names(session, document_id)
        return GeneratedDocumentMeta(
            values={name: value for name, value, origin in rows if origin == FieldOrigin.GENERATED}
        )

    @staticmethod
    def ingest_facts(document: Document) -> IntakeResult:
        """The intake FACTS of a document (no bytes — no replayable stage reads them)."""
        return IntakeResult(
            source_hash=document.source_hash,
            source_format=document.format,
            page_count=document.page_count or 0,
        )


__all__ = ["ReplaySourceFacade"]
