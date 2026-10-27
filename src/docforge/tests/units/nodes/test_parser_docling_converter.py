"""The standard Docling parser's converter build: the OCR / table knobs reach PdfPipelineOptions, and
the OCR, layout and table batches run one page at a time, which keeps a multi-page scan's peak RSS
under the parse watchdog (#163) with the same text. Fake `docling.*` modules are injected only for
the `_build_converter` call, as for the granite node, so the test stays offline.
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from shared_libs.pipelines.ingest.nodes.parse.parser.docling.config import ParserDoclingConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.docling.core import ParserDoclingNode


def _install_fake_docling(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    """Inject fake docling.* modules so _build_converter's lazy imports resolve and are captured."""

    def _module(name: str, **attrs: object) -> ModuleType:
        mod = ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    class _DocumentConverter:
        def __init__(self, format_options: dict) -> None:
            captured["format_options"] = format_options

    class _PdfFormatOption(SimpleNamespace):
        pass

    class _PdfPipelineOptions(SimpleNamespace):
        """Docling's defaults for the fields under test: batches of 4 pages."""

        def __init__(self) -> None:
            super().__init__(ocr_batch_size=4, layout_batch_size=4, table_batch_size=4)

    _module("docling", datamodel=None, document_converter=None)
    _module("docling.datamodel")
    _module("docling.datamodel.base_models", InputFormat=SimpleNamespace(PDF="pdf"))
    _module("docling.datamodel.pipeline_options", PdfPipelineOptions=_PdfPipelineOptions)
    _module(
        "docling.document_converter",
        DocumentConverter=_DocumentConverter,
        PdfFormatOption=_PdfFormatOption,
    )


def test_build_converter_runs_ocr_layout_and_tables_one_page_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batches of 1 instead of docling's 4: a lower multi-page peak RSS, the same output."""
    captured: dict = {}
    _install_fake_docling(monkeypatch, captured)

    node = ParserDoclingNode(id="p", config=ParserDoclingConfig())
    node._build_converter()

    options = captured["format_options"]["pdf"].pipeline_options
    assert options.ocr_batch_size == 1
    assert options.layout_batch_size == 1
    assert options.table_batch_size == 1


@pytest.mark.parametrize(("do_ocr", "do_table_structure"), [(True, False), (False, True)])
def test_build_converter_applies_the_ocr_and_table_knobs(
    monkeypatch: pytest.MonkeyPatch, do_ocr: bool, do_table_structure: bool
) -> None:
    """The node's Config axes land on the PDF pipeline options unchanged."""
    captured: dict = {}
    _install_fake_docling(monkeypatch, captured)

    config = ParserDoclingConfig(do_ocr=do_ocr, do_table_structure=do_table_structure)
    ParserDoclingNode(id="p", config=config)._build_converter()

    options = captured["format_options"]["pdf"].pipeline_options
    assert options.do_ocr is do_ocr
    assert options.do_table_structure is do_table_structure
