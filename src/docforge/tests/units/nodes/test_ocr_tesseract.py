"""The Tesseract provider brick — the OCR-family node backed by the local Tesseract binary
(registration, config shape + knobs, the word-level fold, and _read over a mocked engine).

Everything is offline and dep-free: the engine's ``read`` boundary is monkeypatched to a fixed
word-level dict, so neither the ``tesseract`` binary nor the ``pytesseract``/Pillow packages are
needed. Mirrors how the paddle brick is tested (mock the transport, not the real provider).
"""

import asyncio
import sys
import types

import pytest
from pydantic import ValidationError

from shared_libs.pipelines.nodes.ocr.base import OcrConsumes
from shared_libs.pipelines.nodes.ocr.tesseract.config import OcrTesseractConfig
from shared_libs.pipelines.nodes.ocr.tesseract.core import OcrTesseractNode
from shared_libs.pipelines.nodes.ocr.tesseract.engine import TesseractEngine
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import FigureItem

# ==================== registration + config ====================


def test_tesseract_is_registered_under_the_ocr_family() -> None:
    """The node self-registers as ('ocr', 'tesseract') and surfaces in the palette."""
    assert "tesseract" in NodeRegistry.kinds("ocr")
    assert NodeRegistry.get("ocr", "tesseract") is OcrTesseractNode


def test_config_defaults_to_auto_language_default_engine_and_automatic_segmentation() -> None:
    """The knobs default to 'auto' language (uses the detected doc language), oem 3, psm 3."""
    config = OcrTesseractConfig()
    assert config.lang == "auto"
    assert config.oem == 3
    assert config.psm == 3


def test_config_accepts_multi_language_codes() -> None:
    """A '+'-joined lang string is the whole point of the provider — broad language support."""
    config = OcrTesseractConfig(lang="eng+fra", psm=6)
    assert config.lang == "eng+fra"
    assert config.psm == 6


def test_config_forbids_unknown_fields() -> None:
    """extra='forbid' is inherited from NodeConfig — a typo in the blob fails the build."""
    with pytest.raises(ValidationError):
        OcrTesseractConfig(langs="eng")


def test_config_bounds_the_engine_mode_to_zero_through_three() -> None:
    """oem is a 0-3 knob (0 legacy, 1 LSTM, 2 both, 3 default) — out-of-range fails the build."""
    assert OcrTesseractConfig(oem=1).oem == 1
    with pytest.raises(ValidationError):
        OcrTesseractConfig(oem=4)


# ==================== engine — language resolution (single-source map) ====================


def test_resolve_lang_passes_an_explicit_code_through_verbatim() -> None:
    """An explicit code (incl. '+'-joined) is honoured verbatim — the figure language is ignored."""
    assert TesseractEngine.resolve_lang("eng+fra", "de") == "eng+fra"
    assert TesseractEngine.resolve_lang("deu", "") == "deu"


def test_resolve_lang_auto_maps_the_detected_language_to_its_pack() -> None:
    """'auto' maps DocForge's ISO 639-1 language to its shipped pack, region suffix stripped."""
    assert TesseractEngine.resolve_lang("auto", "fr") == "fra"
    assert TesseractEngine.resolve_lang("AUTO", "EN-US") == "eng"  # case-insensitive + region strip


def test_resolve_lang_auto_falls_back_to_eng_when_unknown_or_empty() -> None:
    """An empty or unmapped detected language falls back to English rather than failing."""
    assert TesseractEngine.resolve_lang("auto", "") == "eng"
    assert TesseractEngine.resolve_lang("auto", "zh") == "eng"  # no shipped pack for Chinese


# ==================== engine — the word-level fold ====================


def test_to_text_joins_words_and_normalizes_confidence() -> None:
    """Real words survive; the -1 layout token is dropped; the mean conf normalizes 0-100 → [0, 1]."""
    data = {
        "text": ["FACTURE", "", "1500"],
        "conf": [90.0, -1.0, 70.0],
    }
    text, score = TesseractEngine.to_text(data)
    assert text == "FACTURE 1500"
    assert score == pytest.approx(0.80)  # mean(90, 70) / 100


def test_to_text_returns_zero_confidence_on_an_empty_reading() -> None:
    """Nothing readable → an empty, zero-confidence reading (a ScoreBelow escalates on it)."""
    assert TesseractEngine.to_text({"text": ["", " "], "conf": [-1.0, -1.0]}) == ("", 0.0)


# ==================== node — _read over a mocked engine ====================


def test_read_maps_engine_data_into_text_and_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """_read passes the config's lang/psm/oem to the engine and folds its data into text + score."""
    captured: dict = {}

    async def _fake_read(image: bytes, lang: str, psm: int, oem: int) -> dict:
        captured["image"] = image
        captured["lang"] = lang
        captured["psm"] = psm
        captured["oem"] = oem
        return {"text": ["hello", "world"], "conf": [80.0, 60.0]}

    monkeypatch.setattr(TesseractEngine, "read", _fake_read)
    node = OcrTesseractNode(id="o", config=OcrTesseractConfig(lang="eng+fra", psm=6, oem=1))
    figure = FigureItem(block_id="f1", image=b"\x89PNG...")
    result = asyncio.run(node.run(OcrConsumes(figure=figure)))

    # 1. The crop bytes + the config knobs reach the engine (explicit lang passed through verbatim).
    assert captured["image"] == b"\x89PNG..."
    assert captured["lang"] == "eng+fra"
    assert captured["psm"] == 6
    assert captured["oem"] == 1

    # 2. The engine's data folds into the figure's read_text + the normalized confidence score.
    assert result.figure.read_text == "hello world"
    assert result.score == pytest.approx(0.70)  # mean(80, 60) / 100
    assert figure.read_text == ""  # the input item was NOT mutated (copy relay)


def test_read_auto_resolves_the_effective_lang_from_the_figure_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """lang='auto' resolves the pack from the figure's detected language ('fr' → 'fra')."""
    captured: dict = {}

    async def _fake_read(image: bytes, lang: str, psm: int, oem: int) -> dict:
        captured["lang"] = lang
        return {"text": ["bonjour"], "conf": [88.0]}

    monkeypatch.setattr(TesseractEngine, "read", _fake_read)
    node = OcrTesseractNode(id="o", config=OcrTesseractConfig())  # lang defaults to 'auto'
    figure = FigureItem(block_id="f1", image=b"png", language="fr")
    asyncio.run(node.run(OcrConsumes(figure=figure)))
    assert captured["lang"] == "fra"


def test_read_degrades_to_empty_on_a_blank_crop(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreadable crop (Tesseract finds nothing) yields a score-0 reading rather than crashing."""

    async def _fake_read(image: bytes, lang: str, psm: int, oem: int) -> dict:
        return {"text": [""], "conf": [-1.0]}

    monkeypatch.setattr(TesseractEngine, "read", _fake_read)
    node = OcrTesseractNode(id="o", config=OcrTesseractConfig())
    result = asyncio.run(node.run(OcrConsumes(figure=FigureItem(block_id="f1", image=b"png"))))
    assert result.figure.read_text == ""
    assert result.score == 0.0


def test_engine_threads_oem_and_psm_into_the_tesseract_config_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engine builds Tesseract's config as '--oem {oem} --psm {psm}' (dep-free fake native stack)."""
    captured: dict = {}

    class _FakeOutput:
        DICT = "dict"

    class _FakePytesseract:
        Output = _FakeOutput
        TesseractNotFoundError = RuntimeError
        TesseractError = RuntimeError

        @staticmethod
        def image_to_data(image: object, lang: str, config: str, output_type: str) -> dict:
            captured["lang"] = lang
            captured["config"] = config
            return {"text": ["ok"], "conf": [90.0]}

    class _FakeImage:
        @staticmethod
        def open(_buffer: object) -> object:
            return object()

    # Inject fake native modules so the lazy import inside __run_sync resolves them (no real binary).
    monkeypatch.setitem(sys.modules, "pytesseract", _FakePytesseract)
    monkeypatch.setitem(sys.modules, "PIL", types.SimpleNamespace(Image=_FakeImage))

    asyncio.run(TesseractEngine.read(b"png", lang="fra", psm=6, oem=1))
    assert captured["lang"] == "fra"
    assert captured["config"] == "--oem 1 --psm 6"
