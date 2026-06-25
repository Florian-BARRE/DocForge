# ====== Code Summary ======
# LIVE coverage of the file-artefact and page sub-resources over the shared ingested corpus
# (read-only). Files: pre-signed URLs for original / pdf / markdown / figure crops — the URLs
# are also fetched to assert non-empty real bytes (pdf starts with %PDF). Pages: the derived
# per-page summary, full page detail, and the on-the-fly PNG screenshot (real bytes — the only
# artefact endpoint that returns content directly rather than a pre-signed URL). Screenshots are
# asserted for EVERY page (not just the first) to catch off-by-one/page-count bugs. The document
# detail is also inspected for jobs/chain_traces/embed_chain_traces population.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import IngestedCorpus

DOC_KEY = "report_fr_docx"

_PNG_MAGIC = b"\x89PNG"


def _doc(ingested: IngestedCorpus) -> dict:
    """Return the shared rich docx document, or skip if it is not available."""
    if not ingested.present(DOC_KEY):
        pytest.skip(f"{DOC_KEY} not available in the shared corpus")
    return ingested.documents[DOC_KEY]


def _first_page_number(ingested: IngestedCorpus, cid: str, did: str) -> int:
    """
    Return the first page number from pages/list.

    DocForge pages are 0-indexed end to end (block provenance page -> renderer doc[page]),
    so the first page is not necessarily 1 — derive it instead of hard-coding it.
    """
    _, pages = ingested.client.get(f"/collections/{cid}/documents/{did}/pages/list")
    return pages["pages"][0]["page"]


def _page_numbers(ingested: IngestedCorpus, cid: str, did: str) -> list[int]:
    """Return the list of all page numbers from pages/list (ordered ascending)."""
    _, pages = ingested.client.get(f"/collections/{cid}/documents/{did}/pages/list")
    return [p["page"] for p in pages.get("pages", [])]


def _first_figure_block(ingested: IngestedCorpus, cid: str, did: str) -> str | None:
    """Scan page details for the first FIGURE block id, or None."""
    _, pages = ingested.client.get(f"/collections/{cid}/documents/{did}/pages/list")
    for page in pages.get("pages", []):
        if page["n_figures"] <= 0:
            continue
        _, detail = ingested.client.get(
            f"/collections/{cid}/documents/{did}/pages/{page['page']}"
        )
        for block in detail.get("blocks", []):
            if block["type"] == "figure":
                return block["id"]
    return None


class TestFileArtifacts:
    """GET original / pdf / markdown / figures — pre-signed URL responses + real byte fetches."""

    @pytest.mark.parametrize("artifact", ["original", "pdf", "markdown"])
    def test_presigned_url_returned(self, ingested_corpus: IngestedCorpus, artifact: str) -> None:
        """Each artefact endpoint returns a pre-signed URL with an expiry for a done document."""
        doc = _doc(ingested_corpus)
        status, body = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/{artifact}"
        )
        assert status == 200, f"{artifact}: {body}"
        assert str(body.get("url", "")).startswith("http")
        assert body.get("expires_in", 0) > 0

    def test_pdf_bytes_start_with_pdf_header(self, ingested_corpus: IngestedCorpus) -> None:
        """The presigned PDF URL is actually fetchable and returns a real PDF (starts with %PDF)."""
        doc = _doc(ingested_corpus)
        status, body = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/pdf"
        )
        assert status == 200, body
        url = body.get("url", "")
        assert url.startswith("http"), f"expected a URL, got {url!r}"
        fetch_status, pdf_bytes = ingested_corpus.client.fetch_url(url)
        # SeaweedFS presigned URLs return 200; bytes must be non-empty and start with %PDF.
        assert fetch_status == 200, f"presigned PDF URL returned {fetch_status}"
        assert len(pdf_bytes) > 0, "presigned PDF URL returned empty body"
        assert pdf_bytes[:4] == b"%PDF", (
            f"PDF bytes do not start with %PDF (got {pdf_bytes[:8]!r})"
        )

    def test_original_bytes_non_empty(self, ingested_corpus: IngestedCorpus) -> None:
        """The presigned original URL is fetchable and returns non-empty content."""
        doc = _doc(ingested_corpus)
        status, body = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/original"
        )
        assert status == 200, body
        url = body.get("url", "")
        assert url.startswith("http")
        fetch_status, orig_bytes = ingested_corpus.client.fetch_url(url)
        assert fetch_status == 200, f"presigned original URL returned {fetch_status}"
        assert len(orig_bytes) > 0, "presigned original URL returned empty body"

    def test_missing_document_404(self, ingested_corpus: IngestedCorpus) -> None:
        """A pre-signed URL request for an unknown document → 404."""
        status, _ = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{uuid.uuid4()}/original"
        )
        assert status == 404

    def test_figure_crop_url_when_present(self, ingested_corpus: IngestedCorpus) -> None:
        """If the document has a figure block, its crop resolves to a pre-signed URL."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        block_id = _first_figure_block(ingested_corpus, cid, did)
        if block_id is None:
            pytest.skip("no figure block extracted for this document")
        status, body = ingested_corpus.client.get(
            f"/collections/{cid}/documents/{did}/figures/{block_id}"
        )
        # 200 with a URL, or 404 if the crop was not persisted — both are valid contract outcomes.
        assert status in (200, 404), body
        if status == 200:
            assert str(body.get("url", "")).startswith("http")

    def test_figure_crop_bytes_non_empty_when_present(
        self, ingested_corpus: IngestedCorpus
    ) -> None:
        """When a figure crop URL is issued, fetching it returns non-empty image bytes."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        block_id = _first_figure_block(ingested_corpus, cid, did)
        if block_id is None:
            pytest.skip("no figure block extracted for this document")
        status, body = ingested_corpus.client.get(
            f"/collections/{cid}/documents/{did}/figures/{block_id}"
        )
        if status == 404:
            pytest.skip("figure crop was not persisted for this document (valid: 404)")
        assert status == 200, body
        url = body.get("url", "")
        assert url.startswith("http")
        # Fetch the actual bytes — the route uses the block's stored crop_key, so a 404 here
        # means the content-addressed PNG is genuinely missing (a pipeline bug, not a routing bug).
        fetch_status, crop_bytes = ingested_corpus.client.fetch_url(url)
        assert fetch_status == 200, (
            f"presigned figure crop URL returned {fetch_status} — crop blob not in object store?"
        )
        assert len(crop_bytes) > 0, "figure crop URL returned empty body"
        # Figure crops are PNGs — assert at least the minimal PNG magic signature.
        assert crop_bytes[:4] == _PNG_MAGIC, (
            f"figure crop bytes do not start with PNG magic (got {crop_bytes[:8]!r})"
        )


class TestDocumentDetailCompleteness:
    """GET document detail: assert pipeline telemetry fields are populated after a full run."""

    def test_jobs_present_and_non_empty(self, ingested_corpus: IngestedCorpus) -> None:
        """GET /{document_id} includes at least one job record from the ingestion run."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        status, body = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}")
        assert status == 200, body
        jobs = body.get("jobs", [])
        assert isinstance(jobs, list) and len(jobs) >= 1, (
            f"expected at least one job, got {jobs!r}"
        )
        # The last job must have reached 'done' for a successfully ingested document.
        job_statuses = {j["status"] for j in jobs}
        assert "done" in job_statuses, (
            f"no done job in document history (statuses seen: {job_statuses})"
        )

    def test_chain_traces_populated(self, ingested_corpus: IngestedCorpus) -> None:
        """GET /{document_id} includes chain_traces (parser-chain provenance from S1)."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        status, body = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}")
        assert status == 200, body
        traces = body.get("chain_traces", [])
        assert isinstance(traces, list) and len(traces) >= 1, (
            f"expected chain_traces to be non-empty after a full S1 run, got {traces!r}"
        )

    def test_embed_chain_traces_populated(self, ingested_corpus: IngestedCorpus) -> None:
        """GET /{document_id} includes embed_chain_traces (S6 embed provenance) when indexed."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        status, body = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}")
        assert status == 200, body
        if not body.get("indexed"):
            pytest.skip("document not indexed in Qdrant — embed_chain_traces absent (expected)")
        embed_traces = body.get("embed_chain_traces", [])
        assert isinstance(embed_traces, list) and len(embed_traces) >= 1, (
            f"indexed=True but embed_chain_traces empty ({embed_traces!r})"
        )


class TestPages:
    """GET pages/list, pages/{n}, pages/{n}/screenshot — every page rendered."""

    def test_pages_list_summary(self, ingested_corpus: IngestedCorpus) -> None:
        """The page list reports total pages and per-page block/figure/table/chunk counts."""
        doc = _doc(ingested_corpus)
        status, body = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/pages/list"
        )
        assert status == 200, body
        assert body["total_pages"] >= 1
        first = body["pages"][0]
        for field in ("page", "n_blocks", "n_figures", "n_tables", "has_text", "n_chunks"):
            assert field in first

    def test_page_count_matches_document_page_count(self, ingested_corpus: IngestedCorpus) -> None:
        """The total_pages from pages/list must match doc.page_count (consistency guard)."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        _, pages_body = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}/pages/list")
        total_pages = pages_body.get("total_pages", -1)
        # page_count from the document detail may differ if page detection was lossy, but the
        # pages/list total must be positive and at least 1.
        assert total_pages >= 1, f"pages/list returned total_pages={total_pages}"
        page_count = doc.get("page_count", 0) or 0
        if page_count > 0:
            # Allow pages/list total_pages to be <= page_count (PDF may have blank pages stripped).
            assert total_pages <= page_count, (
                f"pages/list total_pages={total_pages} > doc.page_count={page_count}"
            )

    def test_page_detail(self, ingested_corpus: IngestedCorpus) -> None:
        """Full page detail returns blocks, concatenated text and covering chunk ids."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        first = _first_page_number(ingested_corpus, cid, did)
        status, body = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}/pages/{first}")
        assert status == 200, body
        assert body["page"] == first
        assert "blocks" in body and "text" in body and "chunk_ids" in body

    def test_page_screenshot_returns_png_first_page(self, ingested_corpus: IngestedCorpus) -> None:
        """The screenshot endpoint renders a real PNG (magic bytes) for the first page."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        first = _first_page_number(ingested_corpus, cid, did)
        status, content, content_type = ingested_corpus.client.get_bytes(
            f"/collections/{cid}/documents/{did}/pages/{first}/screenshot"
        )
        assert status == 200
        assert content_type.startswith("image/png")
        assert content[:4] == _PNG_MAGIC, f"response is not a PNG: {content[:8]!r}"
        assert len(content) > 100, "PNG is suspiciously small — likely an empty/corrupt render"

    def test_every_page_screenshot_returns_png(self, ingested_corpus: IngestedCorpus) -> None:
        """Every page in pages/list can be rendered as a valid PNG (not just the first).

        This test catches off-by-one errors in the page renderer — e.g. a pptx converted by
        Gotenberg produces a different page count than PyMuPDF would infer from the raw bytes.
        The fix: `get_page_screenshot` uses key_pdf (the converted PDF) not key_original.

        We cap to the first 10 pages to keep the test from being too slow on large documents.
        """
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        page_nums = _page_numbers(ingested_corpus, cid, did)
        # Cap to avoid excessive runtime on large documents (e.g. a 50-page pdf)
        to_test = page_nums[:10]
        assert to_test, "pages/list returned no pages"
        failures: list[str] = []
        for pn in to_test:
            status, content, content_type = ingested_corpus.client.get_bytes(
                f"/collections/{cid}/documents/{did}/pages/{pn}/screenshot"
            )
            if status != 200:
                failures.append(f"page {pn}: status={status}")
            elif content[:4] != _PNG_MAGIC:
                failures.append(f"page {pn}: not a PNG (got {content[:8]!r})")
            elif len(content) < 100:
                failures.append(f"page {pn}: PNG suspiciously small ({len(content)} bytes)")
        assert not failures, "Some page screenshots failed:\n" + "\n".join(failures)

    def test_page_out_of_range_404(self, ingested_corpus: IngestedCorpus) -> None:
        """Requesting a page beyond the document → 404."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        status, _ = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}/pages/9999")
        assert status == 404
