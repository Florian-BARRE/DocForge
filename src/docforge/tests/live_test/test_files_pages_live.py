# ====== Code Summary ======
# LIVE coverage of the file-artefact and page sub-resources over the shared ingested corpus
# (read-only). Files: pre-signed URLs for original / pdf / markdown / figure crops. Pages: the
# derived per-page summary, full page detail, and the on-the-fly PNG screenshot (real bytes — the
# only artefact endpoint that returns content directly rather than a pre-signed URL).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import IngestedCorpus

DOC_KEY = "report_fr_docx"


def _doc(ingested: IngestedCorpus) -> dict:
    """Return the shared rich docx document, or skip if it is not available."""
    if not ingested.present(DOC_KEY):
        pytest.skip(f"{DOC_KEY} not available in the shared corpus")
    return ingested.documents[DOC_KEY]


def _first_page_number(ingested: IngestedCorpus, cid: str, did: str) -> int:
    """
    Return the first page's number from pages/list.

    DocForge pages are 0-indexed end to end (block provenance page -> renderer doc[page]),
    so the first page is not necessarily 1 — derive it instead of hard-coding it.
    """
    _, pages = ingested.client.get(f"/collections/{cid}/documents/{did}/pages/list")
    return pages["pages"][0]["page"]


class TestFileArtifacts:
    """GET original / pdf / markdown / figures — pre-signed URL responses."""

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
        block_id = self.__first_figure_block(ingested_corpus, cid, did)
        if block_id is None:
            pytest.skip("no figure block extracted for this document")
        status, body = ingested_corpus.client.get(
            f"/collections/{cid}/documents/{did}/figures/{block_id}"
        )
        # 200 with a URL, or 404 if the crop was not persisted — both are valid contract outcomes.
        assert status in (200, 404), body
        if status == 200:
            assert str(body.get("url", "")).startswith("http")

    @staticmethod
    def __first_figure_block(ingested: IngestedCorpus, cid: str, did: str) -> str | None:
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


class TestPages:
    """GET pages/list, pages/{n}, pages/{n}/screenshot."""

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

    def test_page_detail(self, ingested_corpus: IngestedCorpus) -> None:
        """Full page detail returns blocks, concatenated text and covering chunk ids."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        first = _first_page_number(ingested_corpus, cid, did)
        status, body = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}/pages/{first}")
        assert status == 200, body
        assert body["page"] == first
        assert "blocks" in body and "text" in body and "chunk_ids" in body

    def test_page_screenshot_returns_png(self, ingested_corpus: IngestedCorpus) -> None:
        """The screenshot endpoint renders a real PNG (magic bytes), not a URL."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        first = _first_page_number(ingested_corpus, cid, did)
        status, content, content_type = ingested_corpus.client.get_bytes(
            f"/collections/{cid}/documents/{did}/pages/{first}/screenshot"
        )
        assert status == 200
        assert content_type.startswith("image/png")
        assert content[:4] == b"\x89PNG", "response is not a PNG"

    def test_page_out_of_range_404(self, ingested_corpus: IngestedCorpus) -> None:
        """Requesting a page beyond the document → 404."""
        doc = _doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        status, _ = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}/pages/9999")
        assert status == 404
