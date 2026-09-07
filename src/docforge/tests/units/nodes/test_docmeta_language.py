"""The docmeta/language node — the dedicated, configurable owner of DocumentIR.language.

Language detection moved OUT of the parser mappers (which now emit language="") into this visible
graph node. Locked here:
  1. the stop-word LanguageDetector normalizes real text to an ISO 639-1 code (or "" on no signal),
  2. mode='auto' stamps the detected code onto the IR, falling back to default_language on no signal,
  3. mode='fixed' forces default_language regardless of the text,
  4. the node is PURE — it never mutates the IR it consumes.
"""

import asyncio

from shared_libs.pipelines.ingest.nodes.docmeta.language import (
    DocLanguageConfig,
    DocLanguageConsumes,
    DocLanguageNode,
    LanguageDetector,
)
from shared_libs.public_models import Block, BlockType, DocumentIR, Provenance

_FR_TEXT = (
    "La protection des données personnelles est un droit fondamental qui doit être respecté par "
    "toutes les organisations. Ce document décrit les obligations et les responsabilités de chacun."
)
_EN_TEXT = (
    "The protection of personal data is a fundamental right that must be respected by every "
    "organisation. This document describes the obligations and the responsibilities of everyone."
)


def _ir(text: str) -> DocumentIR:
    """A minimal IR carrying one paragraph block of the given text (language left unset)."""
    return DocumentIR(
        doc_id="d",
        source_hash="h",
        blocks=[
            Block(
                id="d:0",
                block_type=BlockType.PARAGRAPH,
                provenance=Provenance(page=0, bbox=(0.0, 0.0, 1.0, 1.0)),
                reading_order=0,
                text=text,
            )
        ],
    )


def _run(node: DocLanguageNode, ir: DocumentIR) -> DocumentIR:
    """Run the node's async ``run`` and return the produced IR."""
    return asyncio.run(node.run(DocLanguageConsumes(ir=ir))).ir


def test_detector_normalizes_fr_and_en_to_iso_codes() -> None:
    """The lightweight detector returns a normalized ISO 639-1 code from real text, "" on no signal."""
    assert LanguageDetector.detect(_FR_TEXT) == "fr"
    assert LanguageDetector.detect(_EN_TEXT) == "en"
    assert LanguageDetector.detect("") == ""
    assert LanguageDetector.detect("   ") == ""
    assert LanguageDetector.detect("1234 5678 9012") == ""


def test_auto_mode_stamps_the_detected_language_on_the_ir() -> None:
    """mode='auto' (the default) detects over the IR block text and stamps the ISO code."""
    node = DocLanguageNode("language", DocLanguageConfig())
    assert _run(node, _ir(_FR_TEXT)).language == "fr"
    assert _run(node, _ir(_EN_TEXT)).language == "en"


def test_auto_mode_falls_back_to_default_language_when_undetectable() -> None:
    """mode='auto' with no textual signal falls back to the configured default (never a wrong guess)."""
    node = DocLanguageNode("language", DocLanguageConfig(default_language="en"))
    assert _run(node, _ir("42 42 42")).language == "en"
    # An empty default keeps the language unset rather than inventing one.
    bare = DocLanguageNode("language", DocLanguageConfig())
    assert _run(bare, _ir("42 42 42")).language == ""


def test_fixed_mode_forces_the_configured_code_ignoring_the_text() -> None:
    """mode='fixed' stamps default_language verbatim, whatever the text says."""
    node = DocLanguageNode("language", DocLanguageConfig(mode="fixed", default_language="de"))
    # French text, but fixed mode forces 'de'.
    assert _run(node, _ir(_FR_TEXT)).language == "de"


def test_node_is_pure_and_never_mutates_the_input_ir() -> None:
    """The consumed IR must be untouched — the node returns a copy with only language set."""
    node = DocLanguageNode("language", DocLanguageConfig())
    source = _ir(_FR_TEXT)
    produced = _run(node, source)
    assert source.language == ""  # input untouched
    assert produced.language == "fr"  # copy carries the result
    assert produced is not source
