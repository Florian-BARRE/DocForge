"""RunTranslator: block-id remap, chunk UUID minting, content-addressed blobs, named vector
points, and the dedup rule that lives inside ``__register_blob``.

Ported from the scratchpad's test_worker_translator.py, split into one test per axis, plus a
dedicated dedup test (axis 6) that the scratchpad did not isolate — see
[[port-scratchpad-gap-plan]] for the two-identical-artefacts recipe.
"""

import uuid

import pytest
from persistence import RunTranslator

from shared_libs.public_models import (
    Block,
    BlockType,
    Chunk,
    ChunkEmbeddings,
    ChunkRole,
    ChunkVectors,
    DocumentIR,
    FieldOrigin,
    FieldScope,
    FieldType,
    FigureEnrichment,
    FigureKind,
    GeneratedDocumentMeta,
    IntakeResult,
    PageRender,
    PageRenders,
    Provenance,
    RunBundle,
    SparseVector,
)
from shared_libs.services.db.postgresql.tables import BlobKind, MetadataField, SourceKind

DOC = uuid.uuid4()
CROP = b"png-crop-bytes"


def _ir() -> DocumentIR:
    return DocumentIR(
        doc_id="d",
        source_hash="h",
        n_pages=1,
        title="Report",
        blocks=[
            Block(
                id="b0",
                block_type=BlockType.HEADING,
                reading_order=0,
                level=1,
                text="Intro",
                provenance=Provenance(page=0, bbox=(0, 0, 1, 1)),
            ),
            Block(
                id="b1",
                block_type=BlockType.PARAGRAPH,
                reading_order=1,
                text="Cats.",
                parent_id="b0",
                provenance=Provenance(page=0, bbox=(0, 0, 1, 1)),
            ),
            Block(
                id="b2",
                block_type=BlockType.FIGURE,
                reading_order=2,
                provenance=Provenance(page=0, bbox=(0, 0, 1, 1)),
                figure=FigureEnrichment(
                    kind=FigureKind.CHART,
                    crop=CROP,
                    ocr_text="Q1 10",
                    description="A chart.",
                    data_table=[["Q", "V"]],
                ),
            ),
        ],
    )


def _chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="d#c0",
            ordinal=0,
            text="Cats.",
            context="Section: Intro",
            block_ids=["b0", "b1"],
            token_count=2,
            heading_path=["Report", "Intro"],
            generated_meta={"keywords": ["cats"]},
        )
    ]


def _bundle() -> RunBundle:
    return RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=b"pdf-bytes", page_count=1),
        ir=_ir(),
        pages=PageRenders(
            pages=[PageRender(page_number=0, image=b"page-png", width=595, height=842)]
        ),
        chunks=_chunks(),
        document_meta=GeneratedDocumentMeta(values={"summary": "About cats", "ghost": 1}),
        embeddings=ChunkEmbeddings(
            model="m",
            dimension=3,
            items=[
                ChunkVectors(
                    chunk_id="d#c0",
                    dense=[1.0, 2.0, 3.0],
                    sparse=SparseVector(indices=[4], values=[0.5]),
                    fields={"keywords": [9.0, 9.0, 9.0]},
                )
            ],
        ),
    )


def _schema() -> list[MetadataField]:
    return [
        MetadataField(
            id=7,
            collection_id=uuid.uuid4(),
            field_name="keywords",
            field_type=FieldType.KEYWORD_LIST,
            origin=FieldOrigin.GENERATED,
            scope=FieldScope.CHUNK,
            filterable=True,
            semantic=True,
        ),
        MetadataField(
            id=8,
            collection_id=uuid.uuid4(),
            field_name="summary",
            field_type=FieldType.STRING,
            origin=FieldOrigin.GENERATED,
            scope=FieldScope.DOCUMENT,
        ),
    ]


@pytest.fixture
def translated():
    return RunTranslator.translate(
        DOC, _bundle(), _schema(), strategy="structure_aware", config_hash="cfg1"
    )


def test_block_id_remap_applies_everywhere(translated) -> None:
    ids = [b.id for b in translated.payload.blocks]
    assert ids == [f"{DOC}:b0", f"{DOC}:b1", f"{DOC}:b2"]
    assert translated.payload.blocks[1].parent_id == f"{DOC}:b0"
    assert translated.payload.block_figures[0].block_id == f"{DOC}:b2"
    assert all(cb.block_id.startswith(f"{DOC}:") for cb in translated.payload.composition)


def test_chunk_uuid_minted_and_wired_through_composition_and_point(translated) -> None:
    chunk_row = translated.payload.chunks[0]
    assert isinstance(chunk_row.id, uuid.UUID)
    assert chunk_row.text == "Section: Intro\n\nCats."  # stored ENRICHED (decided design)
    assert chunk_row.heading_path == [
        "Report",
        "Intro",
    ]  # section ancestry persisted for hit self-cite
    assert {cb.chunk_id for cb in translated.payload.composition} == {chunk_row.id}
    assert translated.points[0].point_id == str(chunk_row.id)
    assert translated.payload.chunk_metadata[0].field_id == 7  # name -> field_id resolved


def test_blobs_are_content_addressed_and_facts_learned(translated) -> None:
    kinds = {row.kind for row in translated.blob_rows}
    assert kinds == {BlobKind.CANONICAL_PDF, BlobKind.PAGE_RENDER, BlobKind.FIGURE_CROP}
    assert translated.payload.pdf_blob_hash
    assert translated.payload.pages[0].render_blob_hash
    assert translated.payload.block_figures[0].crop_blob_hash
    assert len(translated.objects) == len(translated.blob_rows) == 3
    assert translated.payload.title == "Report"
    assert translated.payload.page_count == 1


def test_title_falls_back_to_the_first_heading_when_the_parser_found_none() -> None:
    """An empty parser title (the HTML->PDF case, which loses <title>) falls back to the document's
    first top-level heading, so the hit/explorer surface a human label rather than an empty string."""
    bundle = _bundle().model_copy(update={"ir": _ir().model_copy(update={"title": ""})})
    translated = RunTranslator.translate(
        DOC, bundle, _schema(), strategy="structure_aware", config_hash="cfg1"
    )
    assert translated.payload.title == "Intro"  # b0, the first level-1 heading


def test_enrichment_rows_and_unknown_doc_field_dropped(translated) -> None:
    enrichment_kinds = {row.kind.value for row in translated.payload.enrichments}
    assert enrichment_kinds == {"classify", "ocr", "vlm", "chart_to_data"}
    assert [meta.field_id for meta in translated.payload.document_metadata] == [
        8
    ]  # 'ghost' dropped


def test_qdrant_point_has_named_vectors_and_lean_payload(translated) -> None:
    point = translated.points[0]
    assert point.dense["content_dense"] == [1.0, 2.0, 3.0]
    assert point.dense["meta_keywords_dense"] == [9.0, 9.0, 9.0]
    assert point.sparse["content_bm25"].indices == [4]
    assert point.payload == {
        "document_id": str(DOC),
        "chunk_index": 0,
        "enabled": True,
        "keywords": ["cats"],
    }
    assert translated.dense_dim == 3


def test_disabled_by_role_chunk_persists_as_a_row_but_gets_no_qdrant_point() -> None:
    """A disabled-by-role chunk reaches persistence (inspectable, re-enablable) with NO vector.

    This is the P3 delivery contract at the bundle -> persistence boundary: the chunker keeps
    furniture as chunks and the embedder skips them, so the bundle carries a body chunk WITH a
    vector item and a header/footer chunk WITHOUT one. Both must become chunk rows; only the body
    one becomes a Qdrant point (linkage is by chunk_id — the disabled chunk is simply not listed).
    """
    bundle = RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=1),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=1, blocks=[]),
        pages=PageRenders(pages=[]),
        chunks=[
            Chunk(chunk_id="d#c0", ordinal=0, text="Cats purr.", role=ChunkRole.BODY),
            Chunk(
                chunk_id="d#c1",
                ordinal=1,
                text="Confidential — page 1",
                role=ChunkRole.HEADER_FOOTER,
            ),
        ],
        embeddings=ChunkEmbeddings(
            model="m", dimension=3, items=[ChunkVectors(chunk_id="d#c0", dense=[1.0, 2.0, 3.0])]
        ),  # body only, furniture skipped
    )
    out = RunTranslator.translate(uuid.uuid4(), bundle, schema=[], strategy="s", config_hash="c")

    # 1. BOTH chunks are persisted as rows — the disabled one is not lost.
    assert {row.chunk_index for row in out.payload.chunks} == {0, 1}
    # 2. The furniture row carries its ROLE (not the "body" server_default) — so it resolves
    #    effective-disabled downstream, not silently re-enabled as body.
    furniture_row = next(r for r in out.payload.chunks if r.chunk_index == 1)
    assert furniture_row.role == ChunkRole.HEADER_FOOTER.value
    # 3. Exactly ONE Qdrant point, for the body chunk — the furniture carries no vector.
    body_uuid = next(r.id for r in out.payload.chunks if r.chunk_index == 0)
    assert len(out.points) == 1
    assert out.points[0].point_id == str(body_uuid)
    # 4. The body point's payload carries the lean `enabled` flag (=true via the role policy), so
    #    the P5 search filter can match on it and the P5 toggle can flip it without re-embedding.
    assert out.points[0].payload["enabled"] is True


def test_html_preview_pdf_is_exposed_as_the_viewable_pdf_and_page_count_from_renders() -> None:
    """A natively-parsed html/md carries no parser PDF (page_count 0) but a VIEW-ONLY preview PDF and
    its page renders. The translator must expose that preview as the viewable PDF (pdf_blob_hash) and
    derive page_count from the renders, so GET /documents/{id} shows a PDF and page_count > 0."""
    bundle = RunBundle(
        ingest=IntakeResult(
            source_hash="h", pdf_content=None, preview_pdf=b"%PDF-preview", page_count=0
        ),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=1, blocks=[]),
        pages=PageRenders(
            pages=[
                PageRender(page_number=0, image=b"pg0", width=1, height=1),
                PageRender(page_number=1, image=b"pg1", width=1, height=1),
            ]
        ),
        chunks=[],
    )
    out = RunTranslator.translate(uuid.uuid4(), bundle, schema=[], strategy="none", config_hash="c")

    # 1. The preview PDF is registered as the viewable PDF (same blob kind as a canonical one).
    assert out.payload.pdf_blob_hash
    assert any(row.kind == BlobKind.CANONICAL_PDF for row in out.blob_rows)
    # 2. page_count falls back to the rendered-page count when the intake count is 0.
    assert out.payload.page_count == 2
    assert len(out.payload.pages) == 2


def _figure_bundle(figure: FigureEnrichment, *, page: int = 0) -> RunBundle:
    """A minimal bundle with a single FIGURE block carrying the given enrichment slot."""
    return RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=1),
        ir=DocumentIR(
            doc_id="d",
            source_hash="h",
            n_pages=1,
            blocks=[
                Block(
                    id="f0",
                    block_type=BlockType.FIGURE,
                    reading_order=0,
                    provenance=Provenance(page=page, bbox=(0, 0, 1, 1)),
                    figure=figure,
                )
            ],
        ),
        pages=PageRenders(pages=[]),
        chunks=[],
    )


def _classify_kinds(out) -> list[str]:
    return [r.kind.value for r in out.payload.enrichments if r.kind.value == "classify"]


def test_no_classify_row_fabricated_when_no_classifier_ran() -> None:
    """A figure left at its parse-time placeholder (kind=PHOTO, no OCR/VLM/chart) must NOT get a
    fabricated CLASSIFY row — the IR must not report a classification that never happened."""
    bundle = _figure_bundle(FigureEnrichment(kind=FigureKind.PHOTO, crop=CROP))
    out = RunTranslator.translate(DOC, bundle, schema=[], strategy="s", config_hash="c")
    assert _classify_kinds(out) == []
    assert out.payload.enrichments == []  # no OCR/VLM/chart either — nothing ran


def test_real_photo_classification_with_a_vlm_result_persists_a_classify_row() -> None:
    """A genuine PHOTO classification (evidenced by a downstream VLM description) still writes a
    CLASSIFY row — the placeholder value is only suppressed when NOTHING enriched the figure."""
    bundle = _figure_bundle(
        FigureEnrichment(kind=FigureKind.PHOTO, crop=CROP, description="A cat on a mat.")
    )
    out = RunTranslator.translate(DOC, bundle, schema=[], strategy="s", config_hash="c")
    classify = [r for r in out.payload.enrichments if r.kind.value == "classify"]
    assert [r.text for r in classify] == ["photo"]


def test_non_placeholder_kind_alone_persists_a_classify_row() -> None:
    """A decorative skip (no OCR/VLM, but a non-placeholder kind) is a real classifier decision → a
    CLASSIFY row, even though no meaning slot is filled."""
    bundle = _figure_bundle(FigureEnrichment(kind=FigureKind.DECORATIVE, crop=CROP))
    out = RunTranslator.translate(DOC, bundle, schema=[], strategy="s", config_hash="c")
    classify = [r for r in out.payload.enrichments if r.kind.value == "classify"]
    assert [r.text for r in classify] == ["decorative"]


def test_page_is_scanned_and_source_kind_derived_from_scanned_text_figures() -> None:
    """is_scanned and source_kind are DERIVED from the enrich classification: a page holding a
    SCANNED_TEXT figure is scanned; a document with some (not all) scanned pages is MIXED."""
    bundle = RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=2),
        ir=DocumentIR(
            doc_id="d",
            source_hash="h",
            n_pages=2,
            blocks=[
                Block(
                    id="f0",
                    block_type=BlockType.FIGURE,
                    reading_order=0,
                    provenance=Provenance(page=0, bbox=(0, 0, 1, 1)),
                    figure=FigureEnrichment(kind=FigureKind.SCANNED_TEXT, crop=CROP),
                )
            ],
        ),
        pages=PageRenders(
            pages=[
                PageRender(page_number=0, image=b"pg0", width=1, height=1),
                PageRender(page_number=1, image=b"pg1", width=1, height=1),
            ]
        ),
        chunks=[],
    )
    out = RunTranslator.translate(uuid.uuid4(), bundle, schema=[], strategy="s", config_hash="c")
    by_page = {p.page_number: p.is_scanned for p in out.payload.pages}
    assert by_page == {0: True, 1: False}
    assert out.payload.source_kind == SourceKind.MIXED


def test_source_kind_digital_born_when_no_scanned_pages_and_none_without_renders() -> None:
    """No scanned figure → DIGITAL_BORN; no rendered pages at all → None (leave the admission-time
    provisional value untouched rather than assert a kind the run cannot support)."""
    digital = RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=1),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=1, blocks=[]),
        pages=PageRenders(pages=[PageRender(page_number=0, image=b"pg0", width=1, height=1)]),
        chunks=[],
    )
    out = RunTranslator.translate(uuid.uuid4(), digital, schema=[], strategy="s", config_hash="c")
    assert out.payload.pages[0].is_scanned is False
    assert out.payload.source_kind == SourceKind.DIGITAL_BORN

    no_renders = RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=0),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=0, blocks=[]),
        pages=PageRenders(pages=[]),
        chunks=[],
    )
    out2 = RunTranslator.translate(
        uuid.uuid4(), no_renders, schema=[], strategy="s", config_hash="c"
    )
    assert out2.payload.source_kind is None


def test_point_id_is_deterministic_across_runs_and_scoped_to_the_document() -> None:
    """Deterministic UUID v5 point ids: the same (document, chunk) yields the SAME id across two
    runs (idempotent upsert), while a different document yields a different id."""
    run_a = RunTranslator.translate(DOC, _bundle(), _schema(), strategy="s", config_hash="cfg1")
    # A second run of the same document — even under a different config — must remint the same id.
    run_b = RunTranslator.translate(DOC, _bundle(), _schema(), strategy="s", config_hash="cfg2")
    other_doc = RunTranslator.translate(
        uuid.uuid4(), _bundle(), _schema(), strategy="s", config_hash="cfg1"
    )
    id_a = run_a.payload.chunks[0].id
    assert id_a == run_b.payload.chunks[0].id
    assert run_a.points[0].point_id == str(id_a) == run_b.points[0].point_id
    assert other_doc.payload.chunks[0].id != id_a


def test_identical_artefact_bytes_are_deduplicated_into_one_blob_row() -> None:
    """Two PageRenders with IDENTICAL bytes must register exactly one blob row/object."""
    bundle = RunBundle(
        ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=2),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=2, blocks=[]),
        pages=PageRenders(
            pages=[
                PageRender(page_number=0, image=b"same-bytes", width=1, height=1),
                PageRender(page_number=1, image=b"same-bytes", width=1, height=1),
            ]
        ),
        chunks=[],
    )
    out = RunTranslator.translate(uuid.uuid4(), bundle, schema=[], strategy="none", config_hash="d")
    assert len(out.blob_rows) == 1
    assert len(out.objects) == 1
    assert len(out.payload.pages) == 2
    assert out.payload.pages[0].render_blob_hash == out.payload.pages[1].render_blob_hash
