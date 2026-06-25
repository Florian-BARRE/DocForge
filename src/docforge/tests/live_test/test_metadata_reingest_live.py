# ====== Code Summary ======
# LIVE coverage of per-document mutations that depend on an actually-ingested document:
# metadata update (+/- reindex, removal, schema validation), document staleness after an
# index-invalidating config change, reingest (default + force), and the dedup short-circuit on
# identical re-upload. Each test gets its own isolated collection with one rich docx ingested.

# ====== Standard Library Imports ======
from __future__ import annotations

from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import CORPUS_METADATA_SCHEMA


@pytest.fixture
def doc_collection(make_collection, live_client, corpus):
    """Create an isolated collection with one rich docx ingested and indexed."""
    # 1. Collection with the corpus metadata schema, accepting docx
    collection = make_collection(supported_formats=["docx"], metadata_schema=CORPUS_METADATA_SCHEMA)
    cid = collection["id"]

    # 2. Ingest the rich docx with starting metadata and wait for chunks
    doc = corpus.get("report_fr_docx")
    status, ing = live_client.ingest_doc(cid, doc, metadata={"dossier": "D-001", "sujet": "rapport"})
    assert status in (200, 202), ing
    document = live_client.wait_done(cid, ing["doc_id"])
    if (document.get("chunk_count") or 0) == 0:
        pytest.skip("docx did not produce chunks in this environment")

    return SimpleNamespace(cid=cid, did=ing["doc_id"], client=live_client, doc=doc)


class TestMetadataUpdate:
    """POST /{document_id}/update — merge-patch user metadata, optional index sync."""

    def test_update_value_without_reindex(self, doc_collection) -> None:
        """A metadata patch is merged and reflected without reindexing."""
        c = doc_collection
        status, body = c.client.post(
            f"/collections/{c.cid}/documents/{c.did}/update",
            {"metadata": {"dossier": "D-999"}, "reindex": False},
        )
        assert status == 200, body
        assert "dossier" in body["changed_fields"]
        assert body["reindexed"] is False
        fresh = c.client.get(f"/collections/{c.cid}/documents/{c.did}")[1]
        assert fresh["user_meta"]["dossier"] == "D-999"

    def test_update_with_reindex_syncs_or_warns(self, doc_collection) -> None:
        """reindex=True syncs the filterable field into the index (or warns if disabled)."""
        c = doc_collection
        status, body = c.client.post(
            f"/collections/{c.cid}/documents/{c.did}/update",
            {"metadata": {"dossier": "D-777"}, "reindex": True},
        )
        assert status == 200, body
        assert body["reindexed"] is True or body.get("warning"), body

    def test_remove_key_with_null(self, doc_collection) -> None:
        """Setting a key to null removes it from user metadata."""
        c = doc_collection
        c.client.post(f"/collections/{c.cid}/documents/{c.did}/update",
                      {"metadata": {"dossier": None}})
        fresh = c.client.get(f"/collections/{c.cid}/documents/{c.did}")[1]
        assert "dossier" not in fresh["user_meta"]

    def test_unknown_field_rejected_422(self, doc_collection) -> None:
        """An unknown field under unknown_field_policy=reject → 422."""
        c = doc_collection
        status, _ = c.client.post(
            f"/collections/{c.cid}/documents/{c.did}/update",
            {"metadata": {"not_in_schema": "x"}},
        )
        assert status == 422


class TestStaleness:
    """A document becomes stale when the collection's index-invalidating config changes."""

    def test_document_stale_after_embedding_change(self, doc_collection) -> None:
        """After an embedding-model change the existing document reports stale + reasons."""
        c = doc_collection
        # 1. Fresh document is not stale
        assert c.client.get(f"/collections/{c.cid}/documents/{c.did}")[1]["stale"] is False

        # 2. Change the embedding model (index-invalidating) on the collection
        status, _ = c.client.post(f"/collections/{c.cid}/config/update",
                                  {"patch": {"embedding_model": "BAAI/bge-m3-alt"}})
        assert status == 200

        # 3. The previously-processed document is now stale with explained reasons
        fresh = c.client.get(f"/collections/{c.cid}/documents/{c.did}")[1]
        assert fresh["stale"] is True
        assert fresh["stale_reasons"], "stale document should carry reasons"


class TestReingest:
    """POST /{document_id}/reingest — re-run the pipeline (cache-cheap unless force)."""

    def test_reingest_default_returns_202(self, doc_collection) -> None:
        """A default reingest is accepted (Merkle cache keeps unchanged stages cheap)."""
        c = doc_collection
        status, body = c.client.post(
            f"/collections/{c.cid}/documents/{c.did}/reingest", {}
        )
        assert status == 202, body
        assert body["status"] == "pending"
        assert body["job_id"]

    def test_reingest_force_reruns_to_done(self, doc_collection) -> None:
        """force=True bypasses the node cache and the document re-reaches done with chunks."""
        c = doc_collection
        status, body = c.client.post(
            f"/collections/{c.cid}/documents/{c.did}/reingest", {"force": True}
        )
        assert status == 202, body
        # wait_status (not wait_done): the doc still has its prior chunks, so wait_done would
        # return the stale 'pending' snapshot immediately. Poll the STATUS through the
        # pending → running → done transition of the force re-run.
        done = c.client.wait_status(c.cid, c.did, "done")
        assert done.get("status") == "done"
        assert (done.get("chunk_count") or 0) > 0


class TestDedup:
    """Identical re-upload into the same collection short-circuits via source_hash dedup."""

    def test_identical_reupload_is_duplicate(self, doc_collection) -> None:
        """Re-ingesting the same bytes returns duplicate=True and the same document id."""
        c = doc_collection
        status, body = c.client.ingest_doc(c.cid, c.doc, metadata={"dossier": "D-001", "sujet": "rapport"})
        assert status in (200, 202), body
        assert body["duplicate"] is True
        assert str(body["doc_id"]) == str(c.did)
        assert body.get("job_id") is None
