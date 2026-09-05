# ====== Code Summary ======
# RunTranslator — the persistence heart: turns the pipeline's RunBundle into exactly what the
# IngestionFacade persists (payload rows, content-addressed S3 objects + blob registry rows,
# Qdrant points). TWO ID REMAPS live here and nowhere else: pipeline block ids are parser-scoped
# strings that WOULD collide across documents → prefixed with the document UUID; pipeline chunk
# ids are ordinal strings → mapped to DETERMINISTIC UUID v5 point ids derived from
# (document_id, chunk_index), so a re-ingest of the same chunk upserts the SAME Qdrant point.
# Chunk text is stored ENRICHED ONLY (the embedded form: the accumulated context prefix over the
# assembled block content, figures already contributing their OCR/VLM text). The RAW,
# pre-enrichment chunk text is NOT stored and NOT reliably recoverable — stripping the context
# prefix yields the enriched assembly (which already folds in figure OCR/VLM text), and re-joining
# block.text via chunk_block loses the figure contributions and the chunker's exact assembly.

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
    FigureEnrichment,
    FigureKind,
    PageRender,
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
    SourceKind,
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

# The fixed namespace the deterministic chunk point ids (UUID v5) are minted under. A constant,
# private namespace keeps the (document_id, chunk_index) → point-id mapping stable across runs and
# processes without ever colliding with UUIDs minted for other purposes.
_POINT_ID_NAMESPACE = uuid.UUID("6f1e3d0a-8b2c-5e47-9a1f-2c7d4e6b8a90")


@dataclass(slots=True)
class TranslatedRun:
    """Everything the facade persists for one run, ready to hand over."""

    payload: IngestionPayload
    objects: list[S3Object] = field(default_factory=list)
    blob_rows: list[Blob] = field(default_factory=list)
    points: list[QdrantPoint] = field(default_factory=list)
    dense_dim: int = 0
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

    @staticmethod
    def __chunk_point_id(document_id: uuid.UUID, chunk_index: int) -> uuid.UUID:
        """THE chunk-id remap: a deterministic UUID v5 point id keyed on (document, chunk index).

        Deterministic (not random) so re-ingesting the same chunk mints the SAME Qdrant point id and
        the upsert overwrites in place — re-ingest is idempotent instead of orphaning the prior run's
        points.
        """
        return uuid.uuid5(_POINT_ID_NAMESPACE, f"{document_id}:{chunk_index}")

    @staticmethod
    def __scanned_pages(bundle: RunBundle) -> set[int]:
        """The 0-indexed pages carrying a scanned-text region, from the enrich classification.

        PIPELINE.md decides scan-ness at the IR-block grain: a figure classified SCANNED_TEXT is a
        scanned region (text rendered as an image). A page holding one is a scanned page. This is the
        only scan signal the run surfaces — a page docling OCR'd into native-looking text blocks
        carries none, so it reads as not-scanned (the honest floor: under-report, never fabricate).
        """
        return {
            block.provenance.page
            for block in bundle.ir.figure_blocks
            if block.figure is not None and block.figure.kind == FigureKind.SCANNED_TEXT
        }

    @staticmethod
    def __source_kind(page_renders: list[PageRender], scanned_pages: set[int]) -> SourceKind | None:
        """Aggregate the per-page scan signal into the document's acquisition kind.

        Returns None when there are no rendered pages to reason about, so the facade leaves the
        admission-time provisional value untouched instead of asserting a kind the run cannot support.
        A rendered page counts as scanned when it is in ``scanned_pages``.
        """
        # 1. No pages to reason about — do not overwrite the provisional admission value.
        if not page_renders:
            return None
        # 2. Count how many rendered pages carry a scanned-text region.
        scanned_count = sum(1 for render in page_renders if render.page_number in scanned_pages)
        # 3. All / none / some → SCANNED / DIGITAL_BORN / MIXED.
        if scanned_count == 0:
            return SourceKind.DIGITAL_BORN
        if scanned_count == len(page_renders):
            return SourceKind.SCANNED
        return SourceKind.MIXED

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
                cls.__append_figure_enrichments(out, block_id, block.figure)

    @staticmethod
    def __figure_was_classified(figure: FigureEnrichment) -> bool:
        """Whether a classifier genuinely ran on this figure (never assume from the placeholder).

        ``FigureEnrichment.kind`` defaults to PHOTO as a parse-time PLACEHOLDER, so a filled ``kind``
        alone does NOT prove classification happened — a figure the enrich stage never touched still
        reads as PHOTO. A classify result is only provable when the figure carries evidence of
        having gone through enrich: a non-placeholder ``kind`` (the classifier stamped something
        other than the default), or any downstream enrichment slot (OCR/VLM/chart-to-data all run
        AFTER classify, so their presence implies it ran). Absent any evidence, no CLASSIFY row is
        written rather than fabricating a "photo" classification that never happened.
        """
        return (
            figure.kind != FigureKind.PHOTO
            or figure.ocr_text is not None
            or figure.description is not None
            or figure.data_table is not None
        )

    @classmethod
    def __append_figure_enrichments(
        cls, out: TranslatedRun, block_id: str, figure: FigureEnrichment
    ) -> None:
        """One BlockEnrichment row per enrichment a figure genuinely received.

        CLASSIFY is emitted ONLY when a classifier provably ran (see ``__figure_was_classified``);
        OCR/VLM/CHART_TO_DATA rows are emitted only for a filled slot — so a row is never fabricated
        for an enrichment that did not happen.
        """
        # 1. The classification row — honest: written only when a classifier genuinely ran.
        if cls.__figure_was_classified(figure):
            out.payload.enrichments.append(
                BlockEnrichment(
                    block_id=block_id,
                    kind=EnrichmentKind.CLASSIFY,
                    text=figure.kind.value,
                    data=None,
                    status=EnrichmentStatus.OK,
                )
            )
        # 2. One row per filled meaning slot — the figure's OCR text, description and chart data.
        slots = (
            (EnrichmentKind.OCR, figure.ocr_text, None),
            (EnrichmentKind.VLM, figure.description, None),
            (EnrichmentKind.CHART_TO_DATA, None, figure.data_table),
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
        # THE chunk remap: pipeline chunk ids are per-run ordinal strings → deterministic UUID v5
        # point ids keyed on (document_id, chunk_index). Re-ingesting the same chunk yields the SAME
        # point id, so the Qdrant upsert overwrites in place (the delete-by-document in the facade
        # still clears chunks a re-ingest dropped). chunk_index is the stable retrieval-unit identity
        # within a document; block ids are deliberately NOT in the key (parser-scoped, they can shift
        # between runs and would needlessly churn point ids), and document_id is already globally
        # unique so the collection id adds nothing.
        chunk_uuids: dict[str, uuid.UUID] = {
            chunk.chunk_id: cls.__chunk_point_id(document_id, chunk.ordinal)
            for chunk in bundle.chunks
        }
        # Index chunks by id once (was a linear `next(... )` scan per embedding item → O(chunks²)).
        chunk_by_id = {chunk.chunk_id: chunk for chunk in bundle.chunks}

        for chunk in bundle.chunks:
            chunk_uuid = chunk_uuids[chunk.chunk_id]
            # Stored ENRICHED ONLY (the embedded form: context prefix + assembled block content,
            # figures already folded in). The raw pre-enrichment chunk text is NOT stored and NOT
            # reliably recoverable from this row (see the module docstring).
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
                    heading_path=chunk.heading_path or None,
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
            out.points.append(
                QdrantPoint(
                    point_id=str(chunk_uuid),
                    payload=payload,
                    dense=dense,
                    sparse=sparse,
                )
            )
        out.dense_dim = bundle.embeddings.dimension if bundle.embeddings else 0

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
        # A natively-parsed html/md carries no parser PDF (page_count 0), yet its view-only preview
        # yields page renders — fall back to their count so page_count > 0 and the viewer is honest.
        page_renders = bundle.pages.pages if bundle.pages else []
        out.payload.page_count = bundle.ingest.page_count or len(page_renders)
        # The viewable PDF is whichever exists: the canonical parser PDF, else the view-only preview
        # (html/md) — so GET /documents/{id} always exposes a PDF when one could be rendered.
        pdf_bytes = bundle.ingest.pdf_content or bundle.ingest.preview_pdf
        if pdf_bytes:
            out.payload.pdf_blob_hash = cls.__register_blob(
                out, pdf_bytes, BlobKind.CANONICAL_PDF, "application/pdf"
            )

        # 2. Pages + their renders (absent render stage → no page rows, nothing else changes).
        #    is_scanned/source_kind are DERIVED from the enrich classification (PIPELINE.md: no scan
        #    flag upstream — scan-ness is decided at the IR-block grain by enrich). A page carrying a
        #    figure classified SCANNED_TEXT is a scanned page; source_kind aggregates that per page.
        scanned_pages = cls.__scanned_pages(bundle)
        for render in page_renders:
            render_hash = cls.__register_blob(out, render.image, BlobKind.PAGE_RENDER, "image/png")
            out.payload.pages.append(
                Page(
                    document_id=document_id,
                    page_number=render.page_number,
                    width=float(render.width),
                    height=float(render.height),
                    is_scanned=render.page_number in scanned_pages,
                    language=None,
                    render_blob_hash=render_hash,
                )
            )
        # The acquisition-routing fact, derived from the per-page scan signal above (None when there
        # are no rendered pages to reason about → the admission-time provisional value is left as-is).
        out.payload.source_kind = cls.__source_kind(page_renders, scanned_pages)
        # simhash (document + chunk near-dup signature) is left NULL: no ingestion node computes one,
        # so the run carries no signal — honestly defaulted rather than hardcoded, until a near-dup
        # stage lands and writes it here.

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
