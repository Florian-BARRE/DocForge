# ====== Code Summary ======
# LIVE coverage of the real-time SSE streams (Brique C) and the cascade-delete no-orphans
# guarantee. SSE: opening a collection-scoped or global monitoring stream during an active
# ingestion delivers job/stage events. Delete: removing a document purges its Qdrant points and
# chunk rows; dropping a collection removes its Qdrant collection — no orphans anywhere.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest


class TestSseStreams:
    """SSE delivery while a document is being processed."""

    def test_collection_stream_delivers_events(self, make_collection, live_client, corpus) -> None:
        """The collection-scoped stream emits events while its document is ingested."""
        # 1. Fresh collection + a brand-new (non-duplicate) ingest so a job actually runs
        col = make_collection(supported_formats=["docx"])
        cid = col["id"]
        status, ing = live_client.ingest_doc(cid, corpus.get("report_fr_docx"))
        assert status in (200, 202), ing

        # 2. Listen on the scoped stream while the worker processes the document (~seconds)
        events = live_client.collect_sse(
            f"/collections/{cid}/documents/stream", max_events=3, timeout_s=45
        )
        assert events, "no SSE events received on the collection stream during ingestion"

    def test_monitoring_stream_delivers_events(self, make_collection, live_client, corpus) -> None:
        """The global monitoring stream emits events while a document is ingested."""
        # 1. Fresh collection + new ingest to generate global job/stage events
        col = make_collection(supported_formats=["docx"])
        status, ing = live_client.ingest_doc(col["id"], corpus.get("report_fr_docx"))
        assert status in (200, 202), ing

        # 2. The global stream is unfiltered — it should see the activity
        events = live_client.collect_sse("/monitoring/stream", max_events=3, timeout_s=45)
        assert events, "no SSE events received on the monitoring stream during ingestion"


class TestCascadeDelete:
    """Deleting documents / collections leaves no Qdrant or Postgres orphans."""

    def test_document_delete_purges_qdrant_and_chunks(
        self, make_collection, live_client, corpus
    ) -> None:
        """Deleting an indexed document removes its Qdrant points and chunk rows."""
        # 1. Ingest + index a document, confirming it has Qdrant points
        col = make_collection(supported_formats=["docx"])
        cid = col["id"]
        status, ing = live_client.ingest_doc(cid, corpus.get("report_fr_docx"))
        assert status in (200, 202), ing
        did = ing["doc_id"]
        live_client.wait_indexed(cid, did)
        if live_client.qdrant_count(cid, did) <= 0:
            pytest.skip("document was not indexed in Qdrant in this environment")

        # 2. Delete the document — response confirms the cascade
        status, body = live_client.delete(f"/collections/{cid}/documents/{did}/delete")
        assert status == 200, body
        assert body["deleted"] is True

        # 3. No orphans: document gone, Qdrant points gone, chunk rows gone
        assert live_client.get(f"/collections/{cid}/documents/{did}")[0] == 404
        assert live_client.qdrant_count(cid, did) == 0, "ORPHAN: Qdrant points survived delete"
        cstatus, chunks = live_client.get(f"/collections/{cid}/documents/{did}/chunks/list")
        assert cstatus == 404 or chunks.get("total", 0) == 0, "ORPHAN: chunk rows survived delete"

    def test_collection_delete_removes_qdrant_collection(
        self, make_collection, live_client, corpus
    ) -> None:
        """Dropping a collection removes its Qdrant collection (no orphaned vector store)."""
        # 1. Ingest + index so the Qdrant collection exists
        col = make_collection(supported_formats=["docx"])
        cid = col["id"]
        status, ing = live_client.ingest_doc(cid, corpus.get("report_fr_docx"))
        assert status in (200, 202), ing
        live_client.wait_indexed(cid, ing["doc_id"])

        # 2. Drop the collection
        status, body = live_client.delete(f"/collections/{cid}/delete")
        assert status == 200, body
        assert body["deleted"] is True

        # 3. The Qdrant collection must be gone too
        assert not live_client.qdrant_collection_exists(cid), (
            "ORPHAN: Qdrant collection survived collection delete"
        )
