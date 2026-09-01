# ====== Code Summary ======
# Unit tests for the PdfProbeNode page-count admission ceiling (max_pages). Covers: an over-limit
# document fails cleanly with a message naming the actual count and the limit; an under-limit
# document passes through with its count; a stored blob that predates the field still validates and
# falls back to the 2000 default; an explicit per-collection override is respected; and the 0 = no-cap
# escape hatch lets an otherwise over-limit document through.

# ====== Standard Library Imports ======
import io

# ====== Third-Party Library Imports ======
import pytest
from pypdf import PdfWriter

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.nodes.intake.pdf_probe.core import (
    PdfProbeConfig,
    PdfProbeConsumes,
    PdfProbeNode,
)
from shared_libs.public_models import PdfView


def _pdf_of(pages: int) -> bytes:
    """Build a real PDF with the given number of blank pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _node(config: PdfProbeConfig | None = None) -> PdfProbeNode:
    """A PdfProbeNode with the given config (its own defaults when omitted)."""
    return PdfProbeNode(id="pdf_probe", config=config or PdfProbeConfig())


def _consumes(pages: int) -> PdfProbeConsumes:
    """A Consumes carrying a real PDF view of the given page count."""
    return PdfProbeConsumes(pdf=PdfView(content=_pdf_of(pages)))


async def test_over_the_limit_fails_naming_the_count_and_limit() -> None:
    node = _node(PdfProbeConfig(max_pages=3))

    with pytest.raises(ValueError) as excinfo:
        await node.run(_consumes(5))

    message = str(excinfo.value)
    assert "5 pages" in message
    assert "max_pages=3" in message


async def test_under_the_limit_passes_through_with_its_count() -> None:
    node = _node(PdfProbeConfig(max_pages=2000))

    out = await node.run(_consumes(4))

    assert out.probe.page_count == 4


async def test_stored_blob_without_the_field_validates_and_uses_the_2000_default() -> None:
    # A blob that predates the field carries no max_pages; extra="forbid" + a default means it
    # validates and adopts 2000. Proven by a 2001-page doc being rejected against that fallback.
    config = PdfProbeConfig.model_validate({})
    assert config.max_pages == 2000

    with pytest.raises(ValueError) as excinfo:
        await _node(config).run(_consumes(2001))

    assert "max_pages=2000" in str(excinfo.value)


async def test_explicit_override_is_respected() -> None:
    node = _node(PdfProbeConfig(max_pages=10))

    out = await node.run(_consumes(10))  # exactly at the limit is allowed

    assert out.probe.page_count == 10


async def test_zero_disables_the_cap_escape_hatch() -> None:
    node = _node(PdfProbeConfig(max_pages=0))

    out = await node.run(_consumes(50))

    assert out.probe.page_count == 50


async def test_no_pdf_view_is_never_gated() -> None:
    # A source with no PDF view probes to 0 pages and must never trip the ceiling.
    node = _node(PdfProbeConfig(max_pages=1))

    out = await node.run(PdfProbeConsumes(pdf=PdfView(content=None)))

    assert out.probe.page_count == 0
