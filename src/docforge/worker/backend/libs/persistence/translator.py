# ====== Code Summary ======
# RunTranslator — the persistence heart: turns the pipeline's RunBundle into exactly what the
# IngestionFacade persists (payload rows, content-addressed S3 objects + blob registry rows,
# Qdrant points). TWO ID REMAPS live here and nowhere else: pipeline block ids are parser-scoped
# strings that WOULD collide across documents → prefixed with the document UUID; pipeline chunk
# ids are ordinal strings → minted as real UUIDs (the Qdrant point ids). Chunk text is stored
# ENRICHED (the raw text is re-derivable by stripping the context prefix — decided design).

# ====== Standard Library Imports ======
import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import (
    FieldOrigin,
    RunBundle,
    first_heading,
    role_default_enabled,
)
from shared_libs.services.db.facades import IngestionPayload
from shared_libs.services.db.postgresql.tables import (
    Blob,
    BlobKind,
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Chunk,
    ChunkBlock,
    ChunkMetadata,
    DocumentMetadata,
    EnrichmentKind,
    EnrichmentStatus,
    MetadataField,
    Page,
)
from shared_libs.services.db.qdrant import QdrantPoint
from shared_libs.services.db.qdrant.vectors import (
    CHUNK_INDEX_KEY,
    DOCUMENT_ID_KEY,
    ENABLED_KEY,
    SparseVec,
    VectorNames,
)
from shared_libs.services.db.s3 import S3Object


@dataclass(slots=True)
class TranslatedRun:
    """Everything the facade persists for one run, ready to hand over."""

    payload: IngestionPayload
    objects: list[S3Object] = field(default_factory=list)
    blob_rows: list[Blob] = field(default_factory=list)
    points: list[QdrantPoint] = field(default_factory=list)
    dense_dim: int = 0
    colbert_dim: int | None = None
    # O(1) content-hash dedup (was a linear scan of blob_rows per blob → O(blobs²)).
    seen_hashes: set[str] = field(default_factory=set)


class RunTranslator:
    """Static translation of a RunBundle into the facade's persistence inputs."""

    logger = loggerplusplus.bind(identifier="RunTranslator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RunTranslator is a static-only class and cannot be instantiated.")

    @staticmethod
    def __block_id(document_id: uuid.UUID, pipeline_id: str) -> str:
        """THE block-id remap: parser-scoped ids collide across documents — prefix with the doc."""
        return f"{document_id}:{pipeline_id}"


    @classmethod
    def __register_blob(cls, out: TranslatedRun, data: bytes, kind: BlobKind, mime: str) -> str:
        """Content-address one blob (sha256): S3 object + registry row, deduplicated by hash."""
        content_hash = hashlib.sha256(data).hexdigest()
        if content_hash not in out.seen_hashes:
            out.seen_hashes.add(content_hash)
            out.objects.append(S3Object(key=content_hash, data=data, content_type=mime))
            out.blob_rows.append(
                Blob(
                    content_hash=content_hash,
                    s3_key=content_hash,
                    mime_type=mime,
                    size_bytes=len(data),
                    kind=kind,
                )
            )
        return content_hash

    @classmethod
    def __translate_ir(cls, out: TranslatedRun, document_id: uuid.UUID, bundle: RunBundle) -> None:
        """The IR side: blocks (ids remapped), tables, figures (+ crops), enrichment rows."""
        for block in sorted(bundle.ir.blocks, key=lambda item: item.reading_order):
            block_id = cls.__block_id(document_id, block.id)
            out.payload.blocks.append(
                Block(
                    id=block_id,
                    document_id=document_id,
                    block_type=block.block_type.value,
                    page=block.provenance.page,
                    bbox=list(block.provenance.bbox),
                    reading_order=block.reading_order,
                    column_index=0,
                    parent_id=cls.__block_id(document_id, block.parent_id)
                    if block.parent_id
                    else None,
                    level=block.level,
                    text=block.text,
                    is_boilerplate=block.block_type.value == "header_footer",
                    language=block.language,
                    confidence=None,
                )
            )
            if block.table is not None:
                out.payload.block_tables.append(
                    BlockTable(
                        block_id=block_id,
                        n_rows=block.table.n_rows,
                        n_cols=block.table.n_cols,
                        has_header=block.table.has_header,
                        cells=block.table.cells,
                        linearized_md=None,
                    )
                )
            if block.figure is not None:
                crop_hash = (
                    cls.__register_blob(out, block.figure.crop, BlobKind.FIGURE_CROP, "image/png")
                    if block.figure.crop
                    else None
                )
                out.payload.block_figures.append(
                    BlockFigure(block_id=block_id, crop_blob_hash=crop_hash, caption_block_id=None)
                )
                # One enrichment row per filled slot — the figure's meaning, queryable.
                slots = (
                    (EnrichmentKind.CLASSIFY, block.figure.kind.value, None),
                    (EnrichmentKind.OCR, block.figure.ocr_text, None),
                    (EnrichmentKind.VLM, block.figure.description, None),
                    (EnrichmentKind.CHART_TO_DATA, None, block.figure.data_table),
                )
                for kind, text, data in slots:
                    if text is None and data is None:
                        continue
                    out.payload.enrichments.append(
                        BlockEnrichment(
                            block_id=block_id,
                            kind=kind,
                            text=text,
                            data=data,
                            status=EnrichmentStatus.OK,
                        )
                    )

    @classmethod
    def __translate_chunks(
        cls,
        out: TranslatedRun,
        document_id: uuid.UUID,
        bundle: RunBundle,
        schema: list[MetadataField],
        strategy: str,
        config_hash: str,
    ) -> None:
        """The chunk side: UUIDs minted (THE chunk remap), composition, metadata, points."""
        field_ids = {spec.field_name: spec.id for spec in schema}
        filterable = {spec.field_name for spec in schema if spec.filterable}
        chunk_uuids: dict[str, uuid.UUID] = {
            chunk.chunk_id: uuid.uuid4() for chunk in bundle.chunks
        }
        # Index chunks by id once (was a linear `next(... )` scan per embedding item → O(chunks²)).
        chunk_by_id = {chunk.chunk_id: chunk for chunk in bundle.chunks}

        for chunk in bundle.chunks:
            chunk_uuid = chunk_uuids[chunk.chunk_id]
            # Stored ENRICHED (decided design) — the raw text is re-derivable from the context.
            out.payload.chunks.append(
                Chunk(
                    id=chunk_uuid,
                    document_id=document_id,
                    config_hash=config_hash,
                    chunk_index=chunk.ordinal,
                    strategy=strategy,
                    parent_id=None,
                    text=chunk.enriched_text,
                    token_count=chunk.token_count,
                    role=chunk.role.value,
                    simhash=None,
                    is_indexed=False,
                )
            )
            out.payload.composition.extend(
                ChunkBlock(
                    chunk_id=chunk_uuid,
                    block_id=cls.__block_id(document_id, block_id),
                    position=position,
                )
                for position, block_id in enumerate(chunk.block_ids)
            )
            for name, value in chunk.generated_meta.items():
                if name not in field_ids:
                    cls.logger.warning(
                        f"Generated chunk field '{name}' absent from schema — dropped"
                    )
                    continue
                out.payload.chunk_metadata.append(
                    ChunkMetadata(
                        chunk_id=chunk_uuid,
                        field_id=field_ids[name],
                        value=value,
                        origin=FieldOrigin.GENERATED,
                    )
                )

        # The vectors, chunk-linked through the SAME minted UUIDs (the point ids).
        # No embed stage → no points, dense_dim 0 — the task then skips Qdrant entirely.
        items = bundle.embeddings.items if bundle.embeddings else []
        for item in items:
            chunk_uuid = chunk_uuids.get(item.chunk_id)
            if chunk_uuid is None:
                cls.logger.warning(f"Vectors for unknown chunk '{item.chunk_id}' — dropped")
                continue
            source = chunk_by_id[item.chunk_id]
            payload: dict[str, Any] = {
                DOCUMENT_ID_KEY: str(document_id),
                CHUNK_INDEX_KEY: source.ordinal,
                # Lean filterable scalar the P5 search filter matches on. Sourced from the single
                # role policy (not hardcoded true) so it stays honest if the embed policy changes:
                # today only effective-enabled chunks are embedded, so every ingested point is true.
                ENABLED_KEY: role_default_enabled(source.role),
                **{
                    name: value
                    for name, value in source.generated_meta.items()
                    if name in filterable
                },
            }
            dense = {VectorNames.CONTENT_DENSE: item.dense} if item.dense else {}
            dense.update(
                {VectorNames.field_dense(name): vector for name, vector in item.fields.items()}
            )
            sparse = (
                {
                    VectorNames.CONTENT_SPARSE: SparseVec(
                        indices=item.sparse.indices, values=item.sparse.values
                    )
                }
                if item.sparse
                else {}
            )
            # The ColBERT multi-vector lands on the CONTENT point only — never mirrored onto the
            # meta_<slug>_dense metadata vectors built from item.fields above.
            multivector = {VectorNames.CONTENT_COLBERT: item.colbert} if item.colbert else {}
            out.points.append(
                QdrantPoint(
                    point_id=str(chunk_uuid),
                    payload=payload,
                    dense=dense,
                    sparse=sparse,
                    multivector=multivector,
                )
            )
        out.dense_dim = bundle.embeddings.dimension if bundle.embeddings else 0
        # colbert_dim drives whether `ensure` declares the content_colbert multi-vector; None means
        # this embed produced no ColBERT axis, so no ColBERT vector is declared on the collection.
        out.colbert_dim = bundle.embeddings.colbert_dim if bundle.embeddings else None

    @classmethod
    def translate(
        cls,
        document_id: uuid.UUID,
        bundle: RunBundle,
        schema: list[MetadataField],
        strategy: str,
        config_hash: str,
    ) -> TranslatedRun:
        """
        Translate one run's delivery into the facade's persistence inputs.

        Args:
            document_id (uuid.UUID): The admitted document (the id everything is remapped to).
            bundle (RunBundle): The pipeline's delivery.
            schema (list[MetadataField]): The collection's field rows (name → field_id).
            strategy (str): The chunking strategy recorded on every chunk row.
            config_hash (str): The pipeline-config hash recorded on every chunk row.

        Returns:
            TranslatedRun: payload + S3 objects + blob rows + Qdrant points + dense dim.
        """
        out = TranslatedRun(payload=IngestionPayload())

        # 1. Document facts + the canonical PDF blob. The title falls back to the document's first
        #    top-level heading when the parser extracted none (the HTML->PDF path loses <title>), so
        #    a search hit and the explorer surface a human label, not an empty string.
        out.payload.title = bundle.ir.title or first_heading(bundle.ir) or None
        out.payload.language = bundle.ir.language
        out.payload.page_count = bundle.ingest.page_count
        if bundle.ingest.pdf_content:
            out.payload.pdf_blob_hash = cls.__register_blob(
                out, bundle.ingest.pdf_content, BlobKind.CANONICAL_PDF, "application/pdf"
            )

        # 2. Pages + their renders (absent render stage → no page rows, nothing else changes).
        for render in bundle.pages.pages if bundle.pages else []:
            render_hash = cls.__register_blob(out, render.image, BlobKind.PAGE_RENDER, "image/png")
            out.payload.pages.append(
                Page(
                    document_id=document_id,
                    page_number=render.page_number,
                    width=float(render.width),
                    height=float(render.height),
                    is_scanned=False,
                    language=None,
                    render_blob_hash=render_hash,
                )
            )

        # 3. Document-scope generated metadata (field ids resolved from the schema).
        field_ids = {spec.field_name: spec.id for spec in schema}
        doc_values = bundle.document_meta.values if bundle.document_meta else {}
        for name, value in doc_values.items():
            if name not in field_ids:
                cls.logger.warning(
                    f"Generated document field '{name}' absent from schema — dropped"
                )
                continue
            out.payload.document_metadata.append(
                DocumentMetadata(
                    document_id=document_id,
                    field_id=field_ids[name],
                    value=value,
                    origin=FieldOrigin.GENERATED,
                )
            )

        # 4. The IR (block-id remap) and the chunks (UUID minting + points).
        cls.__translate_ir(out, document_id, bundle)
        cls.__translate_chunks(out, document_id, bundle, schema, strategy, config_hash)
        cls.logger.info(
            f"Translated run for {document_id}: {len(out.payload.blocks)} blocks, "
            f"{len(out.payload.chunks)} chunks, {len(out.objects)} blobs, {len(out.points)} points"
        )
        return out


__all__ = ["RunTranslator", "TranslatedRun"]
