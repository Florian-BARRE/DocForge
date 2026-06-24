# ====== Code Summary ======
# LIVE coverage of the admission/contract rejection paths against real collections: unsupported
# format (415, incl. the Markdown corpus negative), oversized file (413), empty upload (400),
# metadata-schema breaches (422: missing-required / bad-type / bad-enum / unknown-field) and the
# unknown-collection 404. These assert the gate BEFORE any pipeline work happens.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# Metadata schema with a required field, a typed field and an enum field — to exercise every
# metadata-validation branch. unknown_field_policy defaults to "reject".
STRICT_SCHEMA = [
    {"field_name": "ref", "field_type": "string", "required": True,
     "filterable": True, "lexical": False, "semantic": False},
    {"field_name": "count", "field_type": "number", "required": False,
     "filterable": True, "lexical": False, "semantic": False},
    {"field_name": "level", "field_type": "enum", "required": False,
     "filterable": True, "lexical": False, "semantic": False, "enum_values": ["low", "high"]},
]


class TestFormatAndSizeGates:
    """415 / 413 / 400 — file-level admission."""

    def test_markdown_unsupported_returns_415(self, make_collection, live_client, corpus) -> None:
        """The Markdown corpus negative is rejected when .md is not a supported format."""
        col = make_collection(supported_formats=["docx"])
        status, _ = live_client.ingest_doc(col["id"], corpus.get("note_md"))
        assert status == 415

    def test_unknown_extension_returns_415(self, make_collection, live_client) -> None:
        """An extension absent from supported_formats → 415."""
        col = make_collection(supported_formats=["pdf"])
        status, _ = live_client.ingest(col["id"], "weird.xyz", b"some bytes here", None)
        assert status == 415

    def test_oversized_file_returns_413(self, make_collection, live_client, corpus) -> None:
        """A supported file that exceeds max_file_size_bytes → 413 (not 415)."""
        col = make_collection(supported_formats=["docx"], max_file_size_bytes=100)
        status, _ = live_client.ingest_doc(col["id"], corpus.get("report_fr_docx"))
        assert status == 413

    def test_empty_file_returns_400(self, make_collection, live_client) -> None:
        """A zero-byte upload → 400 before any format/size check."""
        col = make_collection(supported_formats=["docx"])
        status, _ = live_client.ingest(col["id"], "empty.docx", b"", None)
        assert status == 400


class TestMetadataGate:
    """422 — metadata payload vs collection schema."""

    @pytest.fixture
    def strict_collection(self, make_collection):
        """A docx collection with a strict metadata schema (reject unknown fields)."""
        return make_collection(supported_formats=["docx"], metadata_schema=STRICT_SCHEMA)

    def test_missing_required_field_422(self, strict_collection, live_client, corpus) -> None:
        """Omitting a required field → 422."""
        status, _ = live_client.ingest_doc(strict_collection["id"], corpus.get("report_fr_docx"),
                                           metadata={"count": 3})
        assert status == 422

    def test_bad_type_422(self, strict_collection, live_client, corpus) -> None:
        """A number field given a string → 422."""
        status, _ = live_client.ingest_doc(strict_collection["id"], corpus.get("report_fr_docx"),
                                           metadata={"ref": "R1", "count": "not-a-number"})
        assert status == 422

    def test_bad_enum_422(self, strict_collection, live_client, corpus) -> None:
        """An enum value outside the allowed set → 422."""
        status, _ = live_client.ingest_doc(strict_collection["id"], corpus.get("report_fr_docx"),
                                           metadata={"ref": "R1", "level": "medium"})
        assert status == 422

    def test_unknown_field_422(self, strict_collection, live_client, corpus) -> None:
        """An unknown field under reject policy → 422."""
        status, _ = live_client.ingest_doc(strict_collection["id"], corpus.get("report_fr_docx"),
                                           metadata={"ref": "R1", "surprise": "x"})
        assert status == 422

    def test_valid_metadata_admitted(self, strict_collection, live_client, corpus) -> None:
        """A fully valid payload is admitted (202)."""
        status, body = live_client.ingest_doc(strict_collection["id"], corpus.get("report_fr_docx"),
                                              metadata={"ref": "R1", "count": 3, "level": "high"})
        assert status in (200, 202), body


class TestNotFound:
    """404 — unknown collection on ingest."""

    def test_ingest_unknown_collection_404(self, live_client) -> None:
        """Ingesting into a non-existent collection → 404 (file non-empty so the 400 gate passes)."""
        status, _ = live_client.ingest(str(uuid.uuid4()), "x.docx", b"%PDF-not-really", None)
        assert status == 404
