# ====== Code Summary ======
# LIVE end-to-end ingestion + structure coverage across EVERY corpus format. Each ingestable
# document (docx/xlsx/pptx/html generated + doc/xls/ppt/pdf committed) is ingested once via the
# shared `ingested_corpus` fixture, then asserted to have run the full real pipeline:
# Gotenberg -> Docling -> chunk -> embed -> Qdrant. Structural minimums come from the catalog
# specs (conservative, since Gotenberg->Docling is lossy); the calibration test also prints the
# observed figure/table counts so the specs can be tightened to real values.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.corpus import CorpusManifest
from tests.corpus.catalog import CATALOG
from tests.live_test.conftest import IngestedCorpus

# Keys DocForge is expected to accept; legacy keys are skipped per-test when their committed
# fixture is absent (the corpus generator simply omits them).
INGESTABLE_KEYS: list[str] = [s.key for s in CATALOG if s.ingestable]

# The four always-present generated formats (no external tooling needed to produce them).
GENERATED_KEYS: set[str] = {"report_fr_docx", "data_fr_xlsx", "report_fr_pptx", "report_fr_html"}


def _doc_or_skip(ingested: IngestedCorpus, key: str) -> dict:
    """Return the ingested document payload for a key, skipping if it was never ingested."""
    if key not in ingested.documents:
        pytest.skip(f"{key} not ingested (legacy fixture absent or enqueue failed)")
    return ingested.documents[key]


@pytest.mark.parametrize("key", INGESTABLE_KEYS)
class TestCorpusIngestion:
    """Per-format assertions over the once-ingested shared corpus."""

    def test_status_done(self, ingested_corpus: IngestedCorpus, key: str) -> None:
        """The document reaches terminal status 'done' (not 'error')."""
        doc = _doc_or_skip(ingested_corpus, key)
        assert doc.get("status") == "done", (
            f"{key}: status={doc.get('status')!r} errors={doc.get('pipeline_errors')}"
        )

    def test_detected_language(
        self, ingested_corpus: IngestedCorpus, corpus: CorpusManifest, key: str
    ) -> None:
        """The pipeline detects the document's authored language (fr/en/es) when one is declared."""
        doc = _doc_or_skip(ingested_corpus, key)
        expected = corpus.get(key).spec.expected_language
        if expected is None:
            pytest.skip(f"{key}: no expected language declared (data/negative document)")
        assert doc.get("language") == expected, (
            f"{key}: detected language {doc.get('language')!r}, expected {expected!r}"
        )

    def test_produces_chunks(
        self, ingested_corpus: IngestedCorpus, corpus: CorpusManifest, key: str
    ) -> None:
        """The pipeline produces at least the spec's minimum number of retrieval chunks."""
        doc = _doc_or_skip(ingested_corpus, key)
        spec = corpus.get(key).spec
        assert (doc.get("chunk_count") or 0) >= spec.min_chunks, (
            f"{key}: chunk_count={doc.get('chunk_count')} < {spec.min_chunks}"
        )

    def test_page_count(
        self, ingested_corpus: IngestedCorpus, corpus: CorpusManifest, key: str
    ) -> None:
        """The recovered page count meets the spec's minimum."""
        doc = _doc_or_skip(ingested_corpus, key)
        spec = corpus.get(key).spec
        assert (doc.get("page_count") or 0) >= spec.min_pages, (
            f"{key}: page_count={doc.get('page_count')} < {spec.min_pages}"
        )

    def test_blocks_extracted(self, ingested_corpus: IngestedCorpus, key: str) -> None:
        """Docling recovered at least one IR block from the document."""
        doc = _doc_or_skip(ingested_corpus, key)
        assert (doc.get("block_count") or 0) > 0, f"{key}: no blocks extracted"

    def test_original_and_markdown_available(
        self, ingested_corpus: IngestedCorpus, key: str
    ) -> None:
        """The original upload is retained and S1 produced a Markdown view."""
        doc = _doc_or_skip(ingested_corpus, key)
        assert doc.get("has_original") is True, f"{key}: original missing"
        assert doc.get("has_markdown") is True, f"{key}: markdown view missing"

    def test_pdf_artifact_available(self, ingested_corpus: IngestedCorpus, key: str) -> None:
        """A canonical PDF artefact exists (Gotenberg-converted, or the native PDF itself)."""
        doc = _doc_or_skip(ingested_corpus, key)
        assert doc.get("has_pdf") is True, f"{key}: canonical PDF missing"

    def test_indexed_in_qdrant(self, ingested_corpus: IngestedCorpus, key: str) -> None:
        """S6 embedded the chunks: Qdrant holds points (source of truth) + the doc reads indexed."""
        doc = _doc_or_skip(ingested_corpus, key)
        client = ingested_corpus.client
        # Wait on Qdrant points (the definitive signal); chunks (S4) commit just before S6 indexes.
        refreshed = client.wait_indexed(ingested_corpus.collection_id, doc["id"])
        points = client.qdrant_count(ingested_corpus.collection_id, doc["id"])
        assert points > 0, f"{key}: no Qdrant points for the document (got {points})"
        # The derived `indexed` flag must agree with the real Qdrant state.
        assert refreshed.get("indexed") is True, f"{key}: Qdrant has points but document not marked indexed"

    def test_structure_meets_minimums(
        self, ingested_corpus: IngestedCorpus, corpus: CorpusManifest, key: str
    ) -> None:
        """
        Page/figure/table counts meet the (conservative) spec minimums.

        Also prints the observed counts so the catalog minimums can be calibrated to the real
        Docling output (run with `-s` to see the `[calib]` lines).
        """
        doc = _doc_or_skip(ingested_corpus, key)
        spec = corpus.get(key).spec
        status, pages = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/pages/list"
        )
        assert status == 200, f"{key}: pages/list returned {status}"
        figures = sum(p["n_figures"] for p in pages["pages"])
        tables = sum(p["n_tables"] for p in pages["pages"])
        print(
            f"[calib] {key}: pages={pages['total_pages']} figures={figures} "
            f"tables={tables} chunks={doc.get('chunk_count')} blocks={doc.get('block_count')}"
        )
        assert pages["total_pages"] >= spec.min_pages
        assert figures >= spec.min_figures
        assert tables >= spec.min_tables


def test_all_generated_formats_ingested(ingested_corpus: IngestedCorpus) -> None:
    """Every always-present generated format ingested and reached 'done'."""
    # 1. The four generated formats must all be present (legacy may be absent if unbaked)
    present = set(ingested_corpus.documents.keys())
    missing = GENERATED_KEYS - present
    assert not missing, f"generated formats not ingested: {missing}"

    # 2. None of the ingested documents ended in an error state
    for key, doc in ingested_corpus.documents.items():
        assert doc.get("status") == "done", f"{key}: status={doc.get('status')!r}"
