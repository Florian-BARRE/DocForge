# ====== Code Summary ======
# Guards the collection-transfer import NUL boundary (audit finding #1): RowDeserializer strips U+0000
# from every text/jsonb field as a bundle row is deserialized, so a .dcexport produced BEFORE the
# ingestion-path fix (or a hand-crafted one) re-imports cleanly instead of re-triggering the Postgres
# UntranslatableCharacterError on the INSERT. Pure/serviceless — Postgres' actual NUL rejection is
# proven in tests/db/test_nul_jsonb_persistence.py; here we prove the deserializer heals the values.
# The NUL is built with chr(0) so this source file never contains a raw null byte.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Internal Project Imports ======
from collection_transfer.restore import RemapContext, RowDeserializer

from shared_libs.public_models import FieldOrigin

_NUL = chr(0)


def _document_data(old_id: str) -> dict:
    """The JSONL document-row shape the importer streams, with a NUL in each external text field."""
    return {
        "id": old_id,
        "source_hash": f"hash-{uuid.uuid4().hex}",
        "pdf_blob_hash": None,
        "filename": f"rap{_NUL}port.pdf",
        "format": "pdf",
        "mime_type": "application/pdf",
        "file_size": 2048,
        "page_count": 3,
        "language": f"fr{_NUL}",
        "source_kind": "digital_born",
        "title": f"Le{_NUL} titre",
        "simhash": None,
        "status": "done",
        "pipeline_version": "v1",
        "enabled": True,
        "created_at": datetime.now(UTC).isoformat(),
    }


def test_document_row_is_nul_stripped() -> None:
    old_id = "old-doc-1"
    ctx = RemapContext(field_ids={})
    ctx.documents[old_id] = uuid.uuid4()

    doc = RowDeserializer.document(_document_data(old_id), uuid.uuid4(), ctx)

    assert doc.filename == "rapport.pdf"
    assert doc.title == "Le titre"
    assert doc.language == "fr"


def test_document_metadata_value_is_nul_stripped() -> None:
    # The exact prod-crash column: chunk/document metadata `value` (a JSONB list of generated statements).
    old_doc = "old-doc-2"
    ctx = RemapContext(field_ids={"author": 33})
    ctx.documents[old_doc] = uuid.uuid4()
    data = {
        "document_id": old_doc,
        "field_name": "author",
        "value": ["L’AFD est un établissement.", f"service{_NUL} fait."],
        "origin": FieldOrigin.GENERATED.value,
    }

    row = RowDeserializer.document_metadata(data, ctx)

    assert row is not None
    assert row.value == ["L’AFD est un établissement.", "service fait."]
