# ====== Code Summary ======
# LiveClient — a thin synchronous HTTP helper for the live integration suite. It talks to the
# running DocForge stack over its published ports (REST API + Qdrant REST) exactly as a real
# client would: multipart ingest, JSON CRUD, document polling, Qdrant point counts, raw binary
# fetches (page screenshots) and short SSE captures. No domain imports — pure transport — so
# these tests exercise the real Gotenberg -> Docling -> TEI -> Qdrant path end to end.
#
# Note: slightly exceeds the ~200-line guideline as a documented cohesive exception — it is a single
# transport class whose methods share one httpx.Client lifecycle and cannot be split without
# fragmenting that lifecycle (same rationale as the existing live-suite files).

# ====== Standard Library Imports ======
from __future__ import annotations

import json
import time
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from tests.corpus import CorpusDocument


class LiveClient(LoggerClass):
    """Synchronous client for end-to-end tests against the running DocForge stack."""

    def __init__(
        self,
        api_url: str,
        qdrant_url: str,
        timeout: float = 90.0,
        api_token: str = "",
    ) -> None:
        """
        Initialize the client.

        Args:
            api_url (str): API root including the version prefix (e.g. .../api/v1).
            qdrant_url (str): Qdrant REST root (e.g. http://localhost:10025).
            timeout (float): Default per-request timeout in seconds.
            api_token (str): Bearer token to send on every request (``Authorization: Bearer
                <token>``). When empty the header is omitted so the client works unchanged
                against an AUTH_ENABLED=false stack (backward-compatible default).
        """
        LoggerClass.__init__(self)
        self._api = api_url.rstrip("/")
        self._qdrant = qdrant_url.rstrip("/")
        self._token = api_token.strip()
        # Build a default-headers map once; when empty the header is absent.
        _default_headers = (
            {"Authorization": f"Bearer {self._token}"} if self._token else {}
        )
        self._http = httpx.Client(timeout=timeout, headers=_default_headers)

    # ─── Liveness ────────────────────────────────────────────────────────────────

    @staticmethod
    def is_live(api_url: str, timeout: float = 3.0) -> bool:
        """Return True if the API health endpoint answers 200 (used to skip the suite)."""
        try:
            resp = httpx.get(f"{api_url.rstrip('/')}/health/ping", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def reranker_live(self, reranker_url: str, timeout: float = 2.0) -> bool:
        """Return True if a TEI reranker answers on its health endpoint."""
        try:
            return self._http.get(f"{reranker_url.rstrip('/')}/health", timeout=timeout).status_code == 200
        except Exception:
            return False

    # ─── Generic JSON verbs ──────────────────────────────────────────────────────

    def get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, dict]:
        """GET a JSON endpoint; return (status_code, parsed_body)."""
        return self.__json(self._http.get(self._api + path, params=params))

    def post(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        """POST a JSON body; return (status_code, parsed_body)."""
        return self.__json(self._http.post(self._api + path, json=body))

    def put(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        """PUT a JSON body; return (status_code, parsed_body)."""
        return self.__json(self._http.put(self._api + path, json=body))

    def delete(self, path: str) -> tuple[int, dict]:
        """DELETE a resource; return (status_code, parsed_body)."""
        return self.__json(self._http.delete(self._api + path))

    def get_bytes(self, path: str) -> tuple[int, bytes, str]:
        """GET a binary endpoint (e.g. page screenshot); return (status, bytes, content_type)."""
        resp = self._http.get(self._api + path)
        return resp.status_code, resp.content, resp.headers.get("content-type", "")

    def fetch_url(self, url: str) -> tuple[int, bytes]:
        """
        Fetch an absolute URL (e.g. a presigned S3 URL) and return (status, bytes).

        Used by live tests to verify that presigned URLs issued by the API are actually
        fetchable and return non-empty content — not just that the URL string exists.

        Args:
            url (str): Absolute URL to fetch (no auth headers added).

        Returns:
            tuple[int, bytes]: HTTP status and raw response body.
        """
        # 1. Fetch without auth headers — presigned URLs carry their own auth signature
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        return resp.status_code, resp.content

    # ─── Ingestion ───────────────────────────────────────────────────────────────

    def ingest(
        self, collection_id: str, filename: str, content: bytes, metadata: dict | None = None
    ) -> tuple[int, dict]:
        """
        Upload a document via multipart/form-data to the ingest endpoint.

        Args:
            collection_id (str): Target collection.
            filename (str): Upload filename (its extension drives format admission).
            content (bytes): Raw file bytes.
            metadata (dict | None): Optional user metadata payload (sent as a JSON form field).

        Returns:
            tuple[int, dict]: (status_code, parsed_body).
        """
        # 1. Build the multipart payload (file + optional metadata JSON field)
        files = {"file": (filename, content, "application/octet-stream")}
        data = {"metadata": json.dumps(metadata)} if metadata is not None else None

        # 2. POST and parse
        url = f"{self._api}/collections/{collection_id}/documents/ingest"
        return self.__json(self._http.post(url, files=files, data=data))

    def ingest_doc(
        self, collection_id: str, doc: CorpusDocument, metadata: dict | None = None
    ) -> tuple[int, dict]:
        """Ingest a corpus document by reading its bytes from disk."""
        return self.ingest(collection_id, doc.filename, doc.read_bytes(), metadata)

    def wait_done(self, collection_id: str, doc_id: str, timeout_s: float = 300.0) -> dict:
        """
        Poll a document until it produces chunks, errors, or the timeout elapses.

        Waiting on chunk_count (not merely status) is robust: status can read "done" a beat
        before the chunk rows commit, and the error state is terminal too.

        Args:
            collection_id (str): The document's collection.
            doc_id (str): The document id to poll.
            timeout_s (float): Maximum seconds to wait.

        Returns:
            dict: The last document payload observed.
        """
        # 1. Poll on a fixed cadence until a terminal condition or the deadline
        deadline = time.time() + timeout_s
        last: dict = {}
        while time.time() < deadline:
            status, body = self.get(f"/collections/{collection_id}/documents/{doc_id}")
            if status == 200:
                last = body
                if (body.get("chunk_count") or 0) > 0 or body.get("status") == "error":
                    return body
            time.sleep(2)
        return last

    def wait_status(
        self, collection_id: str, doc_id: str, target: str = "done", timeout_s: float = 300.0
    ) -> dict:
        """
        Poll a document until its STATUS reaches ``target`` (or terminal ``error``), or timeout.

        Use this instead of :meth:`wait_done` when the document already has chunks from a previous
        run — e.g. a force-reingest. ``wait_done`` keys on ``chunk_count>0`` and would return the
        stale snapshot immediately (the prior chunks survive while the re-run is still pending), so
        it can never observe the pending → running → done transition of a reingest.

        Args:
            collection_id (str): The document's collection.
            doc_id (str): The document id to poll.
            target (str): The status to wait for (default "done").
            timeout_s (float): Maximum seconds to wait.

        Returns:
            dict: The last document payload observed.
        """
        # 1. Poll the status until it reaches the target, errors out, or the deadline passes
        deadline = time.time() + timeout_s
        last: dict = {}
        while time.time() < deadline:
            status, body = self.get(f"/collections/{collection_id}/documents/{doc_id}")
            if status == 200:
                last = body
                if body.get("status") in (target, "error"):
                    return body
            time.sleep(2)
        return last

    def wait_indexed(self, collection_id: str, doc_id: str, timeout_s: float = 120.0) -> dict:
        """
        Poll until the document's vectors are present in Qdrant (the definitive indexing signal).

        Qdrant points are the source of truth for "indexed": chunks (S4) commit a beat before
        embeddings (S6) land in Qdrant, so we poll the Qdrant point count rather than the document
        ``indexed`` flag (which is a derived convenience field).

        Returns:
            dict: The last document payload observed (so callers can also inspect the flag).
        """
        # 1. Poll until Qdrant holds points for the doc, the doc errors, or the deadline passes
        deadline = time.time() + timeout_s
        last: dict = {}
        while time.time() < deadline:
            status, body = self.get(f"/collections/{collection_id}/documents/{doc_id}")
            if status == 200:
                last = body
                if body.get("status") == "error":
                    return body
            if self.qdrant_count(collection_id, doc_id) > 0:
                return last
            time.sleep(2)
        return last

    # ─── Qdrant ──────────────────────────────────────────────────────────────────

    def qdrant_count(self, collection_id: str, doc_id: str | None = None) -> int:
        """Count Qdrant points in a collection, optionally filtered to one document_id."""
        body: dict = {"exact": True}
        if doc_id is not None:
            body["filter"] = {"must": [{"key": "document_id", "match": {"value": doc_id}}]}
        resp = self._http.post(
            f"{self._qdrant}/collections/{collection_id}/points/count", json=body, timeout=15
        )
        if resp.status_code != 200:
            return -1
        return int(resp.json().get("result", {}).get("count", 0))

    def qdrant_collection_exists(self, collection_id: str) -> bool:
        """Return True if the Qdrant collection still exists."""
        return self._http.get(f"{self._qdrant}/collections/{collection_id}", timeout=15).status_code == 200

    # ─── SSE ─────────────────────────────────────────────────────────────────────

    def collect_sse(self, path: str, max_events: int = 5, timeout_s: float = 25.0) -> list[str]:
        """
        Open an SSE stream and collect up to ``max_events`` `data:` lines (or until timeout).

        Keepalive comments are ignored. A read timeout simply returns whatever was collected,
        so callers can assert "the stream connected and delivered N events" without flakiness.

        When a token was supplied at construction time it is appended as ``?token=<token>`` to the
        SSE URL in addition to the Authorization header. Browser EventSource cannot send headers, so
        the server's SSE dependency (``require_principal_sse``) accepts the query parameter as a
        fallback — this mirrors the real browser path.

        Returns:
            list[str]: The raw payloads of the captured `data:` events.
        """
        # 1. Append the ?token= query parameter for SSE routes (header also present via default
        #    headers, but the query param is the browser-compatible path we want to exercise).
        sse_path = path
        if self._token:
            separator = "&" if "?" in path else "?"
            sse_path = f"{path}{separator}token={self._token}"

        # 2. Stream lines until enough events, the deadline, or a read timeout
        events: list[str] = []
        deadline = time.time() + timeout_s
        try:
            with self._http.stream("GET", self._api + sse_path, timeout=timeout_s) as resp:
                for line in resp.iter_lines():
                    if line.startswith("data:"):
                        events.append(line[len("data:"):].strip())
                        if len(events) >= max_events:
                            break
                    if time.time() > deadline:
                        break
        except httpx.TimeoutException:
            self.logger.debug(f"SSE read timed out after collecting {len(events)} events.")
        return events

    # ─── Cleanup ─────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    @staticmethod
    def __json(resp: httpx.Response) -> tuple[int, dict]:
        """Return (status_code, parsed-json-or-raw) without raising on error responses."""
        try:
            payload = resp.json()
        except (json.JSONDecodeError, ValueError):
            payload = {"_raw": resp.text}
        return resp.status_code, payload
