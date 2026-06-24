# ====== Code Summary ======
# LIVE coverage of the chunks sub-resource. Read paths (list / get / 404) run on the shared
# ingested corpus. The mutating update path runs on an ISOLATED collection so corrections never
# contaminate the shared corpus other tests rely on. Update covers text correction, the
# both-fields-missing 422 guard, and the optional content re-embed.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import IngestedCorpus

DOC_KEY = "report_fr_docx"


def _shared_doc(ingested: IngestedCorpus) -> dict:
    """Return the shared rich docx document, or skip if unavailable."""
    if not ingested.present(DOC_KEY):
        pytest.skip(f"{DOC_KEY} not available in the shared corpus")
    return ingested.documents[DOC_KEY]


class TestChunksRead:
    """GET chunks/list and chunks/{id} over the shared corpus."""

    def test_list_returns_chunks(self, ingested_corpus: IngestedCorpus) -> None:
        """The chunk list is paginated and each chunk carries its text + provenance."""
        doc = _shared_doc(ingested_corpus)
        status, body = ingested_corpus.client.get(
            f"/collections/{ingested_corpus.collection_id}/documents/{doc['id']}/chunks/list"
        )
        assert status == 200, body
        assert body["total"] >= 1
        chunk = body["chunks"][0]
        for field in ("id", "raw_text", "embed_text", "token_count", "strategy", "block_ids"):
            assert field in chunk

    def test_get_single_chunk(self, ingested_corpus: IngestedCorpus) -> None:
        """A chunk can be fetched by id and materializes its full text."""
        doc = _shared_doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        listing = ingested_corpus.client.get(f"/collections/{cid}/documents/{did}/chunks/list")[1]
        chunk_id = listing["chunks"][0]["id"]
        status, body = ingested_corpus.client.get(
            f"/collections/{cid}/documents/{did}/chunks/{chunk_id}"
        )
        assert status == 200, body
        assert body["id"] == chunk_id
        assert body["raw_text"]

    def test_unknown_chunk_404(self, ingested_corpus: IngestedCorpus) -> None:
        """An unknown chunk id → 404."""
        doc = _shared_doc(ingested_corpus)
        cid, did = ingested_corpus.collection_id, doc["id"]
        status, _ = ingested_corpus.client.get(
            f"/collections/{cid}/documents/{did}/chunks/{uuid.uuid4()}"
        )
        assert status == 404


class TestChunkUpdate:
    """POST chunks/{id}/update on an isolated collection (mutation must not leak)."""

    @pytest.fixture
    def chunked_doc(self, make_collection, live_client, corpus):
        """Isolated collection with one docx ingested; yields (cid, did, first_chunk_id)."""
        # 1. Ingest a docx into a throwaway collection and grab its first chunk
        collection = make_collection(supported_formats=["docx"])
        cid = collection["id"]
        doc = corpus.get("report_fr_docx")
        status, ing = live_client.ingest_doc(cid, doc)
        assert status in (200, 202), ing
        document = live_client.wait_done(cid, ing["doc_id"])
        if (document.get("chunk_count") or 0) == 0:
            pytest.skip("docx produced no chunks in this environment")
        listing = live_client.get(f"/collections/{cid}/documents/{ing['doc_id']}/chunks/list")[1]
        return cid, ing["doc_id"], listing["chunks"][0]["id"]

    def test_update_raw_text(self, live_client, chunked_doc) -> None:
        """Correcting raw_text persists the new value."""
        cid, did, chunk_id = chunked_doc
        status, body = live_client.post(
            f"/collections/{cid}/documents/{did}/chunks/{chunk_id}/update",
            {"raw_text": "Texte corrigé pour le test.", "reindex": False},
        )
        assert status == 200, body
        assert body["raw_text"] == "Texte corrigé pour le test."
        assert body["reindexed"] is False

    def test_update_requires_a_field_422(self, live_client, chunked_doc) -> None:
        """Neither raw_text nor embed_text → 422."""
        cid, did, chunk_id = chunked_doc
        status, _ = live_client.post(
            f"/collections/{cid}/documents/{did}/chunks/{chunk_id}/update", {"reindex": False}
        )
        assert status == 422

    def test_update_with_reindex_reembeds_or_warns(self, live_client, chunked_doc) -> None:
        """reindex=True re-embeds the content vectors (or warns when embedding is disabled)."""
        cid, did, chunk_id = chunked_doc
        status, body = live_client.post(
            f"/collections/{cid}/documents/{did}/chunks/{chunk_id}/update",
            {"embed_text": "Titre\nTexte d'embed corrigé.", "reindex": True},
        )
        assert status == 200, body
        assert body["reindexed"] is True or body.get("warning"), body
