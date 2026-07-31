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
import shared_libs.pipelines.ingest.nodes.intake.converter.gotenberg.core as gotenberg_core
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.intake.converter.base.io import ConverterConsumes
from shared_libs.pipelines.ingest.nodes.intake.converter.gotenberg.config import (
    ConverterGotenbergConfig,
)
from shared_libs.pipelines.ingest.nodes.intake.format_probe.helpers import FormatProbeHelpers
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    CollectionContract,
    FieldOrigin,
    FieldType,
    MetadataFieldSpec,
    SourceDocument,
    SourceProbe,
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
        {
            "node_type": "action",
            "id": "admit",
            "family": "intake",
            "kind": "admission",
            "config": {"unknown_field_policy": "reject"},
        },
        {
            "node_type": "action",
            "id": "probe",
            "family": "intake",
            "kind": "format_probe",
            "config": {},
        },
        {
            "node_type": "action",
            "id": "convert",
            "family": "converter",
            "kind": "gotenberg",
            "config": {"base_url": "http://gotenberg:3000"},
        },
        {
            "node_type": "action",
            "id": "pdf_probe",
            "family": "intake",
            "kind": "pdf_probe",
            "config": {},
        },
        {
            "node_type": "action",
            "id": "content_address",
            "family": "intake",
            "kind": "content_address",
            "config": {},
        },
    ],
    "transitions": [
        {"from_node_id": "probe", "to_node_id": "admit"},
        {"from_node_id": "admit", "to_node_id": "convert"},
        {"from_node_id": "convert", "to_node_id": "pdf_probe"},
        {"from_node_id": "pdf_probe", "to_node_id": "content_address"},
    ],
    "bindings": {
        "probe": {"source": {"source": "run", "field_name": "source"}},
        "admit": {
            "source": {"source": "run", "field_name": "source"},
            "probe": {"source": "node", "node_id": "probe", "field_name": "probe"},
            "contract": {"source": "run", "field_name": "contract"},
        },
        "convert": {
            "source": {"source": "node", "node_id": "admit", "field_name": "source"},
            "probe": {"source": "node", "node_id": "probe", "field_name": "probe"},
        },
        "pdf_probe": {"pdf": {"source": "node", "node_id": "convert", "field_name": "pdf"}},
        "content_address": {
            "source": {"source": "node", "node_id": "admit", "field_name": "source"},
            "source_probe": {"source": "node", "node_id": "probe", "field_name": "probe"},
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
            MetadataFieldSpec(
                field_name="departement",
                field_type=FieldType.STRING,
                required=True,
                enum_values=["finance", "rh"],
            ),
            MetadataFieldSpec(field_name="annee", field_type=FieldType.INTEGER),
            MetadataFieldSpec(
                field_name="resume",
                field_type=FieldType.STRING,
                origin=FieldOrigin.GENERATED,
                semantic=True,
            ),
        ],
    )


async def test_valid_pdf_run_hashes_passes_through_and_counts_pages(group, contract) -> None:
    source = SourceDocument(
        filename="rapport.pdf",
        content=PDF_BYTES,
        declared_meta={"departement": "finance", "annee": 2024},
    )
    output, _record = await FlowEngine().execute(group, {"source": source, "contract": contract})
    result = output.ingest
    assert result.source_hash == hashlib.sha256(PDF_BYTES).hexdigest()
    assert result.pdf_content == PDF_BYTES
    assert result.page_count == 1


REJECTION_CASES = [
    pytest.param(
        SourceDocument(filename="x.exe", content=b"MZ", declared_meta={"departement": "finance"}),
        id="format",
    ),
    pytest.param(
        SourceDocument(
            filename="x.pdf", content=b"%" * 2_000_000, declared_meta={"departement": "finance"}
        ),
        id="size",
    ),
    pytest.param(
        SourceDocument(filename="x.pdf", content=PDF_BYTES, declared_meta={}), id="required_missing"
    ),
    pytest.param(
        SourceDocument(
            filename="x.pdf",
            content=PDF_BYTES,
            declared_meta={"departement": "finance", "inconnu": 1},
        ),
        id="unknown_field",
    ),
    pytest.param(
        SourceDocument(
            filename="x.pdf", content=PDF_BYTES, declared_meta={"departement": "juridique"}
        ),
        id="enum",
    ),
    pytest.param(
        SourceDocument(
            filename="x.pdf",
            content=PDF_BYTES,
            declared_meta={"departement": "finance", "annee": "2024"},
        ),
        id="type",
    ),
    pytest.param(
        SourceDocument(
            filename="x.pdf",
            content=PDF_BYTES,
            declared_meta={"departement": "finance", "resume": "x"},
        ),
        id="generated_supplied",
    ),
    pytest.param(
        SourceDocument(
            filename="x.pdf", content=b"MZ\x90\x00", declared_meta={"departement": "finance"}
        ),
        id="spoofed_extension",
    ),
    pytest.param(
        SourceDocument(filename="x.pdf", content=b"", declared_meta={"departement": "finance"}),
        id="empty_file",
    ),
]


@pytest.mark.parametrize("source", REJECTION_CASES)
async def test_admission_rejects_every_invalid_case(group, contract, source) -> None:
    _output, record = await FlowEngine().execute(group, {"source": source, "contract": contract})
    admit_record = record.children[1]
    assert admit_record.status.value == "failed"
    assert record.status.value == "failed"


# ===================== preview-PDF channel (html/md view-only render) =====================
# The Gotenberg converter now ALSO emits a view-only preview PDF for html/md — a channel decoupled
# from parsing (the parser still reads the original bytes natively) that only feeds the page-render +
# viewable-PDF. Gotenberg is a service, so its Chromium routes are mocked here.

PREVIEW_BYTES = b"%PDF-1.7 preview-render"


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    """Records every Gotenberg POST (route + files) and returns fixed PDF bytes."""

    calls: list = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def post(self, route: str, files=None) -> _FakeResponse:
        _FakeClient.calls.append((route, files))
        return _FakeResponse(PREVIEW_BYTES)


def _gotenberg_node() -> "gotenberg_core.ConverterGotenbergNode":
    return gotenberg_core.ConverterGotenbergNode(
        id="convert", config=ConverterGotenbergConfig(base_url="http://gotenberg:3000")
    )


async def test_html_gets_a_view_only_preview_pdf_and_no_parser_pdf(monkeypatch) -> None:
    _FakeClient.calls = []
    monkeypatch.setattr(gotenberg_core.httpx, "AsyncClient", _FakeClient)
    source = SourceDocument(filename="page.html", content=b"<html><body><h1>Hi</h1></body></html>")
    probe = SourceProbe(format="html", mime_type="text/html", file_size=len(source.content))

    out = await _gotenberg_node().run(ConverterConsumes(source=source, probe=probe))

    # The parser PDF stays None (html is parsed natively), but the view-only preview is produced.
    assert out.pdf.content is None
    assert out.pdf.preview_content == PREVIEW_BYTES
    assert [route for route, _files in _FakeClient.calls] == ["/forms/chromium/convert/html"]


async def test_markdown_preview_uses_the_markdown_route_with_an_index_wrapper(monkeypatch) -> None:
    _FakeClient.calls = []
    monkeypatch.setattr(gotenberg_core.httpx, "AsyncClient", _FakeClient)
    source = SourceDocument(filename="notes.md", content=b"# Title\n\nBody text.")
    probe = SourceProbe(format="md", mime_type="text/markdown", file_size=len(source.content))

    out = await _gotenberg_node().run(ConverterConsumes(source=source, probe=probe))

    assert out.pdf.content is None
    assert out.pdf.preview_content == PREVIEW_BYTES
    route, files = _FakeClient.calls[0]
    assert route == "/forms/chromium/convert/markdown"
    uploaded = [payload[0] for _field, payload in files]  # ("files", (name, bytes, mime))
    assert "index.html" in uploaded and "notes.md" in uploaded  # wrapper + the markdown file


async def test_office_source_keeps_its_parser_pdf_and_has_no_preview(monkeypatch) -> None:
    _FakeClient.calls = []
    monkeypatch.setattr(gotenberg_core.httpx, "AsyncClient", _FakeClient)
    source = SourceDocument(filename="report.docx", content=DOCX_BYTES)
    probe = SourceProbe(
        format="docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size=len(DOCX_BYTES),
    )

    out = await _gotenberg_node().run(ConverterConsumes(source=source, probe=probe))

    # Office keeps the classic single-channel behaviour: the LibreOffice route feeds pdf_content;
    # no preview channel is opened (its PDF already feeds both parse and render).
    assert out.pdf.content == PREVIEW_BYTES
    assert out.pdf.preview_content is None
    assert [route for route, _files in _FakeClient.calls] == ["/forms/libreoffice/convert"]
