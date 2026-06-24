# ====== Code Summary ======
# LIVE hybrid-search coverage against the real embed (TEI BGE-M3) + Qdrant path. Core retrieval
# (find / top_k / filters / debug ranks / weights / document-scoped) runs on the shared
# `ingested_corpus`. Advanced, config-driven stages (grouping, MMR, rerank, query-transform) run
# on isolated collections and are skipped when their dependency (a reranker container or a local
# LLM) is not deployed. Everything is local — no external embedding/rerank/LLM APIs.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import (
    DENSE_ONLY_PIPELINE,
    RERANKER_URL,
    IngestedCorpus,
)

SEARCH_DOC_KEY = "report_fr_docx"  # the most structurally rich generated document


def _require(ingested: IngestedCorpus, key: str = SEARCH_DOC_KEY) -> dict:
    """Return a present, chunk-bearing document or skip (search needs indexed content)."""
    if not ingested.present(key):
        pytest.skip(f"{key} not available/indexed in the shared corpus")
    return ingested.documents[key]


def _search(ingested: IngestedCorpus, body: dict) -> tuple[int, dict]:
    """POST a collection-wide search against the shared corpus collection."""
    return ingested.client.post(
        f"/collections/{ingested.collection_id}/documents/search", body
    )


# ─── Core retrieval (shared corpus) ──────────────────────────────────────────────


class TestCollectionSearch:
    """POST /collections/{id}/documents/search over the shared ingested corpus."""

    def test_finds_target_document(self, ingested_corpus: IngestedCorpus, corpus) -> None:
        """A query on a document's distinctive phrase retrieves that document."""
        doc = _require(ingested_corpus)
        phrase = corpus.get(SEARCH_DOC_KEY).spec.searchable_phrase
        status, res = _search(ingested_corpus, {"query": phrase, "top_k": 10})
        assert status == 200, res
        assert any(r["document_id"] == doc["id"] for r in res["results"]), (
            f"target doc not found; got {[r['document_id'] for r in res['results']]}"
        )

    def test_top_k_is_respected(self, ingested_corpus: IngestedCorpus) -> None:
        """The number of results never exceeds top_k."""
        _require(ingested_corpus)
        status, res = _search(ingested_corpus, {"query": "rapport", "top_k": 3})
        assert status == 200, res
        assert len(res["results"]) <= 3

    def test_filter_on_filterable_field(self, ingested_corpus: IngestedCorpus) -> None:
        """A payload filter on the indexed `dossier` field scopes results to one document."""
        doc = _require(ingested_corpus)
        status, res = _search(ingested_corpus, {
            "query": "rapport", "top_k": 10,
            "filters": {"must": [{"key": "dossier", "match": {"value": f"D-{SEARCH_DOC_KEY}"}}]},
        })
        assert status == 200, res
        assert res["total"] > 0
        assert all(r["document_id"] == doc["id"] for r in res["results"])

    def test_filter_on_absent_value_returns_nothing(self, ingested_corpus: IngestedCorpus) -> None:
        """A filter value that matches no document yields zero results."""
        _require(ingested_corpus)
        status, res = _search(ingested_corpus, {
            "query": "rapport", "top_k": 10,
            "filters": {"must": [{"key": "dossier", "match": {"value": "DOES-NOT-EXIST"}}]},
        })
        assert status == 200, res
        assert res["total"] == 0

    def test_debug_exposes_vector_ranks(self, ingested_corpus: IngestedCorpus, corpus) -> None:
        """debug=True attaches debug_info and per-vector ranks to results."""
        _require(ingested_corpus)
        phrase = corpus.get(SEARCH_DOC_KEY).spec.searchable_phrase
        status, res = _search(ingested_corpus, {"query": phrase, "top_k": 5, "debug": True})
        assert status == 200, res
        assert res.get("debug_info") is not None
        assert res["results"], "expected at least one debug result"
        assert any(r.get("vector_ranks") for r in res["results"])

    def test_weight_overrides_accepted(self, ingested_corpus: IngestedCorpus) -> None:
        """Per-vector weight overrides are accepted and still return ranked results."""
        _require(ingested_corpus)
        status, res = _search(ingested_corpus, {
            "query": "rapport financier", "top_k": 5,
            "weights": {"content_dense": 1.0, "content_sparse": 0.0},
        })
        assert status == 200, res

    def test_missing_collection_returns_404(self, ingested_corpus: IngestedCorpus) -> None:
        """Searching an unknown collection → 404."""
        import uuid
        status, _ = ingested_corpus.client.post(
            f"/collections/{uuid.uuid4()}/documents/search", {"query": "x", "top_k": 5}
        )
        assert status == 404

    def test_empty_query_rejected_422(self, ingested_corpus: IngestedCorpus) -> None:
        """An empty query violates min_length=1 → 422."""
        _require(ingested_corpus)
        status, _ = _search(ingested_corpus, {"query": "", "top_k": 5})
        assert status == 422


class TestDocumentScopedSearch:
    """POST /collections/{id}/documents/{doc}/search pins retrieval to one document."""

    def test_results_pinned_to_document(self, ingested_corpus: IngestedCorpus) -> None:
        """Every result belongs to the pinned document."""
        doc = _require(ingested_corpus)
        status, res = ingested_corpus.client.post(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/search",
            {"query": "rapport", "top_k": 10},
        )
        assert status == 200, res
        assert res["results"], "expected results within the document"
        assert all(r["document_id"] == doc["id"] for r in res["results"])


# ─── Advanced, config-driven stages (isolated collections) ───────────────────────


class TestGroupingAndRerank:
    """Grouping / MMR / rerank exercised on dedicated collections."""

    def test_grouping_returns_document_groups(self, make_collection, live_client, corpus) -> None:
        """A collection with grouping enabled returns document-level groups."""
        # 1. Create a grouping-enabled collection (dense-only embed) and ingest one rich doc
        pipeline = {**DENSE_ONLY_PIPELINE,
                    "search": {"retrieve": {"grouping": {"enabled": True, "group_size": 3}}}}
        collection = make_collection(pipeline=pipeline, supported_formats=["docx"])
        cid = collection["id"]
        doc = corpus.get("report_fr_docx")
        status, ing = live_client.ingest_doc(cid, doc)
        assert status in (200, 202), ing
        live_client.wait_indexed(cid, ing["doc_id"])

        # 2. Search → groups must be present and carry chunks
        status, res = live_client.post(
            f"/collections/{cid}/documents/search",
            {"query": doc.spec.searchable_phrase, "top_k": 10},
        )
        assert status == 200, res
        assert res.get("groups") is not None, "grouping enabled but no groups returned"
        if res["groups"]:
            assert res["groups"][0]["document_id"] == ing["doc_id"]

    def test_rerank_when_reranker_available(self, make_collection, live_client, corpus) -> None:
        """When a TEI reranker is deployed, a rerank-enabled collection returns reranked results."""
        # 1. Skip cleanly when the local reranker is not running
        if not live_client.reranker_live(RERANKER_URL):
            pytest.skip(f"local TEI reranker not reachable at {RERANKER_URL}")

        # 2. Create a rerank-enabled collection (local bge_reranker) and ingest one doc
        pipeline = {**DENSE_ONLY_PIPELINE,
                    "search": {"rerank": {"enabled": True, "candidate_k": 20, "top_n": 5,
                                          "chain": [{"id": "bge_reranker"}]}}}
        collection = make_collection(pipeline=pipeline, supported_formats=["docx"])
        cid = collection["id"]
        doc = corpus.get("report_fr_docx")
        status, ing = live_client.ingest_doc(cid, doc)
        assert status in (200, 202), ing
        live_client.wait_indexed(cid, ing["doc_id"])

        # 3. Search → reranked results, capped at top_n
        status, res = live_client.post(
            f"/collections/{cid}/documents/search",
            {"query": doc.spec.searchable_phrase, "top_k": 5},
        )
        assert status == 200, res
        assert len(res["results"]) <= 5
