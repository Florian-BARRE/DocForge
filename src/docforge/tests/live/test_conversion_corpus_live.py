"""Conversion non-regression smoke against the REAL running stack.

Ingests the reference corpus (``conversion_corpus/corpus.py``: native, scanned and text-layer PDFs,
a Word document through Gotenberg, a plain image) into a throwaway collection and compares, per
document, the stable fingerprint of the result (IR, chunk count + boundaries, metadata, API response
shapes) with the recorded snapshot. A dependency bump or code change that silently alters a
conversion fails here with the exact leaves that moved.

Environment:
    DOCFORGE_LIVE_API_URL      API of the stack to test (default http://127.0.0.1:8000).
    DOCFORGE_SMOKE_RECORD=1    Capture and WRITE the snapshot instead of comparing.
    DOCFORGE_SMOKE_SNAPSHOT    Snapshot file to compare with / write (default snapshots/conversion_corpus.json).
    DOCFORGE_SMOKE_WITH_EMBED=1  Keep the embed stage (needs the BGE host); default: conversion only.

The recorded snapshot is only valid for the pinned conversion stack (docling, pypdf, pypdfium2,
Gotenberg, Pillow): after an INTENDED conversion change, review the diff and re-record it.
"""

import os
from pathlib import Path

import pytest
from conversion_corpus.corpus import CONVERSION_CORPUS
from conversion_corpus.fingerprint import DocumentFingerprinter
from conversion_corpus.ingestor import CorpusIngestor
from conversion_corpus.snapshot_store import SnapshotStore

RECORD = os.environ.get("DOCFORGE_SMOKE_RECORD") == "1"
WITH_EMBED = os.environ.get("DOCFORGE_SMOKE_WITH_EMBED") == "1"
SNAPSHOT_FILE = os.environ.get("DOCFORGE_SMOKE_SNAPSHOT")


def _store() -> SnapshotStore:
    return SnapshotStore(Path(SNAPSHOT_FILE)) if SNAPSHOT_FILE else SnapshotStore()


@pytest.fixture(scope="module")
def corpus_fingerprints(api_client) -> dict:
    """Ingests the whole corpus once and returns ``{document key: fingerprint}``."""
    formats = sorted({document.extension for document in CONVERSION_CORPUS})
    fingerprints: dict = {}
    with CorpusIngestor(api_client, formats, with_embed=WITH_EMBED) as ingestor:
        for document in CONVERSION_CORPUS:
            fingerprints[document.key] = DocumentFingerprinter().fingerprint(
                ingestor.ingest(document)
            )
    if RECORD:
        _store().save(fingerprints)
    return fingerprints


def test_every_corpus_document_ingests_to_a_done_job(corpus_fingerprints) -> None:
    assert set(corpus_fingerprints) == {document.key for document in CONVERSION_CORPUS}
    for key, fingerprint in corpus_fingerprints.items():
        assert fingerprint["job"]["status"] == "done", key
        assert fingerprint["document"]["status"] == "done", key


@pytest.mark.parametrize("document", CONVERSION_CORPUS, ids=lambda d: d.key)
def test_document_fingerprint_matches_the_recorded_snapshot(corpus_fingerprints, document) -> None:
    recorded = _store().load()
    assert document.key in recorded, f"{document.key} not in the snapshot: re-record it"
    drift = SnapshotStore.diff(recorded[document.key], corpus_fingerprints[document.key])
    assert not drift, (
        f"{document.key} ({document.exercises}) drifted from the snapshot:\n  "
        + "\n  ".join(drift[:40])
    )
