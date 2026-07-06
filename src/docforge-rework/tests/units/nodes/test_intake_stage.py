"""Intake stage end to end: byte-signature detection, admission rejections, and a full
blob -> build -> validate -> engine run for a PDF source (no HTTP mocking needed: a PDF passes
through ``BaseConverterNode`` untouched — see [[port-scratchpad-gap-plan]]).

Ported from the scratchpad's test_intake_stage.py.
"""

import hashlib
import io
import uuid
import zipfile

import pytest

import shared_libs.pipelines.ingest.nodes  # noqa: F401 — auto-discovery
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.intake.format_probe.helpers import FormatProbeHelpers
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    CollectionContract,
    FieldOrigin,
    FieldType,
    MetadataFieldSpec,
    SourceDocument,
)


def _pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


PDF_BYTES = _pdf_bytes()
DOCX_BYTES = _docx_bytes()

FORMAT_CHECKS = [
    (PDF_BYTES, "f.pdf", "pdf"),
    (DOCX_BYTES, "f.docx", "docx"),
    (b"<!DOCTYPE html><html></html>", "f.html", "html"),
    (b"hello plain text", "f.txt", "txt"),
    (b"# title", "f.md", "md"),
    (b"\x00\x01\x02\xff", "f.bin", "unknown"),
]


@pytest.mark.parametrize("content,name,expected", FORMAT_CHECKS, ids=[c[2] for c in FORMAT_CHECKS])
def test_format_probe_detects_by_byte_signature(content, name, expected) -> None:
    detected, _mime = FormatProbeHelpers.detect(content, name)
    assert detected == expected


BLOB = {
    "node_type": "group",
    "id": "ingest_stage",
    "nodes": [
        {"node_type": "action", "id": "admit", "family": "intake", "kind": "admission",
         "config": {"unknown_field_policy": "reject"}},
        {"node_type": "action", "id": "probe", "family": "intake", "kind": "format_probe", "config": {}},
        {"node_type": "action", "id": "convert", "family": "converter", "kind": "gotenberg",
         "config": {"base_url": "http://gotenberg:3000"}},
        {"node_type": "action", "id": "pdf_probe", "family": "intake", "kind": "pdf_probe", "config": {}},
        {"node_type": "action", "id": "content_address", "family": "intake",
         "kind": "content_address", "config": {}},
    ],
    "transitions": [
        {"from_node_id": "probe", "to_node_id": "admit"},
        {"from_node_id": "admit", "to_node_id": "convert"},
        {"from_node_id": "convert", "to_node_id": "pdf_probe"},
        {"from_node_id": "pdf_probe", "to_node_id": "content_address"},
    ],
    "bindings": {
        "probe": {"source": {"source": "run", "field_name": "source"}},
        "admit": {"source": {"source": "run", "field_name": "source"},
                  "probe": {"source": "node", "node_id": "probe", "field_name": "probe"},
                  "contract": {"source": "run", "field_name": "contract"}},
        "convert": {"source": {"source": "node", "node_id": "admit", "field_name": "source"},
                    "probe": {"source": "node", "node_id": "probe", "field_name": "probe"}},
        "pdf_probe": {"pdf": {"source": "node", "node_id": "convert", "field_name": "pdf"}},
        "content_address": {
            "source": {"source": "node", "node_id": "admit", "field_name": "source"},
            "pdf": {"source": "node", "node_id": "convert", "field_name": "pdf"},
            "probe": {"source": "node", "node_id": "pdf_probe", "field_name": "probe"},
        },
    },
}


@pytest.fixture(scope="module")
def group():
    built = PipelineBuilder().build(BLOB)
    assert GraphValidator().validate(built) == []
    return built


@pytest.fixture
def contract() -> CollectionContract:
    return CollectionContract(
        collection_id=uuid.uuid4(),
        name="contracts",
        supported_formats=["pdf", "docx"],
        max_file_size_bytes=1_000_000,
        fields=[
            MetadataFieldSpec(field_name="departement", field_type=FieldType.STRING, required=True,
                              enum_values=["finance", "rh"]),
            MetadataFieldSpec(field_name="annee", field_type=FieldType.INTEGER),
            MetadataFieldSpec(field_name="resume", field_type=FieldType.STRING,
                              origin=FieldOrigin.GENERATED, semantic=True),
        ],
    )


async def test_valid_pdf_run_hashes_passes_through_and_counts_pages(group, contract) -> None:
    source = SourceDocument(filename="rapport.pdf", content=PDF_BYTES,
                            declared_meta={"departement": "finance", "annee": 2024})
    output, _record = await FlowEngine().execute(group, {"source": source, "contract": contract})
    result = output.ingest
    assert result.source_hash == hashlib.sha256(PDF_BYTES).hexdigest()
    assert result.pdf_content == PDF_BYTES
    assert result.page_count == 1


REJECTION_CASES = [
    pytest.param(SourceDocument(filename="x.exe", content=b"MZ", declared_meta={"departement": "finance"}), id="format"),
    pytest.param(SourceDocument(filename="x.pdf", content=b"%" * 2_000_000, declared_meta={"departement": "finance"}), id="size"),
    pytest.param(SourceDocument(filename="x.pdf", content=PDF_BYTES, declared_meta={}), id="required_missing"),
    pytest.param(SourceDocument(filename="x.pdf", content=PDF_BYTES,
                                declared_meta={"departement": "finance", "inconnu": 1}), id="unknown_field"),
    pytest.param(SourceDocument(filename="x.pdf", content=PDF_BYTES,
                                declared_meta={"departement": "juridique"}), id="enum"),
    pytest.param(SourceDocument(filename="x.pdf", content=PDF_BYTES,
                                declared_meta={"departement": "finance", "annee": "2024"}), id="type"),
    pytest.param(SourceDocument(filename="x.pdf", content=PDF_BYTES,
                                declared_meta={"departement": "finance", "resume": "x"}), id="generated_supplied"),
    pytest.param(SourceDocument(filename="x.pdf", content=b"MZ\x90\x00", declared_meta={"departement": "finance"}), id="spoofed_extension"),
    pytest.param(SourceDocument(filename="x.pdf", content=b"", declared_meta={"departement": "finance"}), id="empty_file"),
]


@pytest.mark.parametrize("source", REJECTION_CASES)
async def test_admission_rejects_every_invalid_case(group, contract, source) -> None:
    _output, record = await FlowEngine().execute(group, {"source": source, "contract": contract})
    admit_record = record.children[1]
    assert admit_record.status.value == "failed"
    assert record.status.value == "failed"
