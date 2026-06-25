# ====== Code Summary ======
# Fixtures for the LIVE integration suite. Everything here targets the RUNNING DocForge stack
# over its published ports and auto-skips when the stack is unreachable, so a normal unit run is
# never broken. Provides: a shared LiveClient, a session-built synthetic corpus, a once-ingested
# shared collection (read-only tests reuse it), and a collection factory with auto-cleanup
# (mutating tests get isolated, disposable collections).
#
# Collection naming: `e2e-{label}-{YYYYMMDD-HHMMSS}` using the exact creation datetime.
#   - `make_collection`: label defaults to the pytest test node name (derived from `request`).
#   - `ingested_corpus`: label is the stable literal `corpus`.
#   - Callers may pass `label=` to `make_collection` to override the auto-derived name.
#
# Cleanup policy: collections are deleted on teardown by default.
#   - Set env var `DOCFORGE_TEST_KEEP_COLLECTIONS=true` to SKIP deletion and print the kept
#     collection ids + names instead (useful for debugging in the UI after a test run).

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterator

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.corpus import CorpusManifest, load_corpus
from tests.libs.live_client import LiveClient

# ─── Host-facing endpoints (override via env for non-default deployments) ──────────
API_URL = os.environ.get("DOCFORGE_TEST_API_URL", "http://localhost:10020/api/v1")
QDRANT_URL = os.environ.get("DOCFORGE_TEST_QDRANT_URL", "http://localhost:10025")
RERANKER_URL = os.environ.get("DOCFORGE_TEST_RERANKER_URL", "http://localhost:10027")

# Optional bearer token for AUTH_ENABLED=true stacks. When empty (default) the client omits
# the Authorization header entirely, preserving backward compatibility with auth-off deployments.
# Set DOCFORGE_TEST_API_TOKEN to a root API key to run the live suite against a secured stack.
API_TOKEN = os.environ.get("DOCFORGE_TEST_API_TOKEN", "")

# When truthy, teardown skips collection deletion and prints kept ids/names so the user can
# inspect them in the UI. Set DOCFORGE_TEST_KEEP_COLLECTIONS=true to activate.
_KEEP_COLLECTIONS: bool = os.environ.get("DOCFORGE_TEST_KEEP_COLLECTIONS", "").lower() in (
    "1", "true", "yes",
)

# Dense-only embed: the deployed TEI serves BGE-M3 WITHOUT a sparse head, so embed_sparse
# MUST be False (a /embed_sparse call would 424). Shared by every collection the suite creates.
DENSE_ONLY_PIPELINE: dict[str, Any] = {"embed": {"chain": [{"id": "bge_server", "base_url": "http://bge_server:80", "embed_sparse": False}]}}

# Formats the corpus exercises — must be whitelisted on every collection that ingests them.
CORPUS_FORMATS: list[str] = ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "html"]

# Metadata schema used by metadata/search tests: one filterable field + one semantic field.
CORPUS_METADATA_SCHEMA: list[dict[str, Any]] = [
    {"field_name": "dossier", "field_type": "string", "required": False,
     "filterable": True, "lexical": False, "semantic": False},
    {"field_name": "sujet", "field_type": "string", "required": False,
     "filterable": False, "lexical": False, "semantic": True},
]


def _ts() -> str:
    """Return the current datetime as a compact YYYYMMDD-HHMMSS string for collection names."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _collection_name(label: str) -> str:
    """Build the standard e2e collection name: ``e2e-{label}-{YYYYMMDD-HHMMSS}``."""
    return f"e2e-{label}-{_ts()}"


@dataclass
class IngestedCorpus:
    """A shared collection with the whole ingestable corpus already processed."""

    collection_id: str
    collection_name: str
    client: LiveClient
    manifest: CorpusManifest
    # key -> last observed document payload (includes status / chunk_count / page_count).
    documents: dict[str, dict] = field(default_factory=dict)

    def doc_id(self, key: str) -> str:
        """Return the ingested document id for a corpus key."""
        return self.documents[key]["id"]

    def present(self, key: str) -> bool:
        """True if the corpus key was ingested and produced chunks (usable by read tests)."""
        payload = self.documents.get(key)
        return bool(payload and (payload.get("chunk_count") or 0) > 0)


# ─── Core fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def live_client() -> Iterator[LiveClient]:
    """Provide a LiveClient, skipping the whole live suite when the stack is unreachable."""
    # 1. Fail fast (skip) if the API is not answering — keeps unit runs green
    if not LiveClient.is_live(API_URL):
        pytest.skip(f"live DocForge stack not reachable at {API_URL}")
    # 2. Yield a shared client and close it at session end
    client = LiveClient(api_url=API_URL, qdrant_url=QDRANT_URL, api_token=API_TOKEN)
    yield client
    client.close()


@pytest.fixture(scope="session")
def corpus() -> CorpusManifest:
    """Load the committed corpus once per session (documents/<fmt>/; absent files skipped)."""
    return load_corpus()


@pytest.fixture
def make_collection(
    live_client: LiveClient,
    request: pytest.FixtureRequest,
) -> Iterator[Callable[..., dict]]:
    """
    Factory creating disposable collections, each cleaned up after the test.

    The returned callable accepts overrides for the create-collection body; sensible
    corpus-friendly defaults (dense-only embed, all corpus formats) are applied.

    Collection naming: ``e2e-{label}-{YYYYMMDD-HHMMSS}`` where label defaults to the
    pytest test node name. Pass ``label=`` explicitly to override.

    Cleanup: collections are deleted on teardown unless ``DOCFORGE_TEST_KEEP_COLLECTIONS``
    is truthy, in which case ids + names are printed and deletion is skipped.
    """
    # Track (id, name) pairs for teardown reporting
    created: list[tuple[str, str]] = []

    def _make(label: str | None = None, **overrides: Any) -> dict:
        # 1. Derive the label from the test node name when not explicitly provided
        resolved_label = label if label is not None else request.node.name
        # 2. Compose the create body from corpus-friendly defaults + caller overrides
        body: dict[str, Any] = {
            "name": overrides.pop("name", _collection_name(resolved_label)),
            "supported_formats": overrides.pop("supported_formats", CORPUS_FORMATS),
            "pipeline": overrides.pop("pipeline", DENSE_ONLY_PIPELINE),
        }
        body.update(overrides)
        # 3. Create and register for teardown
        status, payload = live_client.post("/collections/create", body)
        assert status == 201, f"collection create failed ({status}): {payload}"
        created.append((payload["id"], body["name"]))
        return payload

    yield _make

    # 4. Teardown: delete or print kept collections depending on the keep flag
    if _KEEP_COLLECTIONS:
        for col_id, col_name in created:
            print(f"\n[KEPT] collection id={col_id} name={col_name!r}")
    else:
        for col_id, _ in created:
            live_client.delete(f"/collections/{col_id}/delete")


@pytest.fixture(scope="session")
def ingested_corpus(live_client: LiveClient, corpus: CorpusManifest) -> Iterator[IngestedCorpus]:
    """
    Create one collection, ingest the entire ingestable corpus once, and share it.

    Read-only tests (search / get / pages / chunks / files / list / jobs) reuse this so the
    expensive Gotenberg -> Docling -> embed path runs a single time per session. Ingestion
    failures are recorded (not raised) so one bad format never blocks the others' tests.

    Collection naming: ``e2e-corpus-{YYYYMMDD-HHMMSS}`` (stable label ``corpus``).
    Cleanup: deleted on session teardown unless ``DOCFORGE_TEST_KEEP_COLLECTIONS`` is truthy.
    """
    # 1. Create the shared collection with the corpus metadata schema
    col_name = _collection_name("corpus")
    status, collection = live_client.post(
        "/collections/create",
        {
            "name": col_name,
            "supported_formats": CORPUS_FORMATS,
            "pipeline": DENSE_ONLY_PIPELINE,
            "metadata_schema": CORPUS_METADATA_SCHEMA,
        },
    )
    assert status == 201, f"shared collection create failed ({status}): {collection}"
    collection_id = collection["id"]
    shared = IngestedCorpus(
        collection_id=collection_id,
        collection_name=col_name,
        client=live_client,
        manifest=corpus,
    )

    # 2. Fire all ingests first (they process concurrently in the worker pool)
    pending: dict[str, str] = {}
    for doc in corpus.ingestable:
        meta = {"dossier": f"D-{doc.key}", "sujet": doc.spec.title}
        ing_status, ing = live_client.ingest_doc(collection_id, doc, metadata=meta)
        if ing_status in (200, 202) and ing.get("doc_id"):
            pending[doc.key] = ing["doc_id"]

    # 3. Wait for each to reach a terminal state and record the final payload
    for key, doc_id in pending.items():
        shared.documents[key] = live_client.wait_done(collection_id, doc_id)

    yield shared

    # 4. Teardown: delete or print kept collection depending on the keep flag
    if _KEEP_COLLECTIONS:
        print(f"\n[KEPT] corpus collection id={collection_id} name={col_name!r}")
    else:
        live_client.delete(f"/collections/{collection_id}/delete")
