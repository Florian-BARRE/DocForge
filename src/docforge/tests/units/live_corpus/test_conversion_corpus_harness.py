"""Offline tests of the conversion-corpus harness (tests/live/conversion_corpus): the fingerprint
must ignore run-volatile values (UUIDs) and must move when a conversion really changes, and the
snapshot diff must name the leaf that moved. The live smoke itself needs the stack."""

# ====== Standard Library Imports ======
import json
import pathlib
import sys

# ====== Third-Party Library Imports ======
import pytest

LIVE_DIR = pathlib.Path(__file__).resolve().parents[2] / "live"
sys.path.insert(0, str(LIVE_DIR))

from conversion_corpus.corpus import CONVERSION_CORPUS  # noqa: E402
from conversion_corpus.fingerprint import DocumentFingerprinter  # noqa: E402
from conversion_corpus.ingestor import IngestedDocument  # noqa: E402
from conversion_corpus.snapshot_store import SnapshotMissingError, SnapshotStore  # noqa: E402


def _ingested(doc_id: str, texts: list[str], chunk_texts: list[str]) -> IngestedDocument:
    blocks = [
        {
            "id": f"{doc_id}:{i}",
            "block_type": "paragraph",
            "page": 0,
            "page_number": 1,
            "bbox": [0.1, 0.2, 0.3, 0.4],
            "reading_order": i,
            "parent_id": None,
            "level": None,
            "text": text,
            "is_boilerplate": False,
            "language": None,
        }
        for i, text in enumerate(texts)
    ]
    chunks = [
        {
            "id": f"{doc_id}:chunk{i}",
            "chunk_index": i,
            "text": text,
            "token_count": len(text.split()),
            "role": "body",
            "strategy": "structure_aware",
            "heading_path": [],
            "page_number": 1,
            "block_ids": [blocks[i]["id"]],
            "metadata": [],
            "enabled": True,
            "is_indexed": False,
        }
        for i, text in enumerate(chunk_texts)
    ]
    return IngestedDocument(
        key="k",
        document_id=doc_id,
        job={"status": "done", "kind": "ingest"},
        document={
            "id": doc_id,
            "format": "pdf",
            "status": "done",
            "source_hash": "h",
            "pdf_blob_hash": "h",
            "chunk_count": len(chunks),
            "created_at": "now",
        },
        chunks=chunks,
        ir={"blocks": blocks, "tables": [], "figures": [], "enrichments": []},
        markdown="\n\n".join(texts),
        trace={"events": [{"node_kind": "docling", "status": "success"}]},
    )


def test_fingerprint_ignores_uuids_and_timestamps() -> None:
    first = DocumentFingerprinter().fingerprint(_ingested("aaa", ["one", "two"], ["one", "two"]))
    second = DocumentFingerprinter().fingerprint(_ingested("bbb", ["one", "two"], ["one", "two"]))
    assert first == second
    assert "created_at" not in first["document"]


def test_fingerprint_moves_when_a_chunk_boundary_moves() -> None:
    before = DocumentFingerprinter().fingerprint(_ingested("a", ["one", "two"], ["one", "two"]))
    after = DocumentFingerprinter().fingerprint(_ingested("a", ["one", "two"], ["one two"]))
    assert before["chunks"]["count"] == 2 and after["chunks"]["count"] == 1
    assert before["chunks"]["boundary_hash"] != after["chunks"]["boundary_hash"]
    assert before["ir"] == after["ir"]


def test_fingerprint_moves_when_ir_text_changes() -> None:
    before = DocumentFingerprinter().fingerprint(_ingested("a", ["one"], ["one"]))
    after = DocumentFingerprinter().fingerprint(_ingested("a", ["One"], ["one"]))
    assert before["ir"]["text_hash"] != after["ir"]["text_hash"]
    assert before["ir"]["structure_hash"] == after["ir"]["structure_hash"]


def test_snapshot_diff_names_the_leaf_that_moved() -> None:
    recorded = {"chunks": {"count": 2, "list": [{"sha": "a"}, {"sha": "b"}]}, "gone": 1}
    current = {"chunks": {"count": 3, "list": [{"sha": "a"}, {"sha": "c"}]}, "new": 2}
    assert SnapshotStore.diff(recorded, current) == [
        "chunks.count: 2 -> 3",
        'chunks.list[1].sha: "b" -> "c"',
        "gone: removed (was 1)",
        "new: added -> 2",
    ]
    assert SnapshotStore.diff(recorded, recorded) == []


def test_snapshot_round_trip_and_missing(tmp_path: pathlib.Path) -> None:
    store = SnapshotStore(tmp_path / "snap.json")
    with pytest.raises(SnapshotMissingError):
        store.load()
    store.save({"doc": {"n": 1}})
    assert store.load() == {"doc": {"n": 1}}


def test_committed_snapshot_covers_every_corpus_document_and_fixture() -> None:
    recorded = SnapshotStore().load()
    assert set(recorded) == {document.key for document in CONVERSION_CORPUS}
    for document in CONVERSION_CORPUS:
        assert document.path.is_file(), document.path
        assert json.dumps(recorded[document.key]["chunks"]["boundary_hash"])
