"""The Tesseract provider brick — the OCR-family node backed by the local Tesseract binary
(registration, config shape + knobs, the word-level fold, and _read over a mocked engine).

Everything is offline and dep-free: the engine's ``read`` boundary is monkeypatched to a fixed
word-level dict, so neither the ``tesseract`` binary nor the ``pytesseract``/Pillow packages are
needed. Mirrors how the paddle brick is tested (mock the transport, not the real provider).
"""

import asyncio

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


def test_config_defaults_to_english_and_automatic_segmentation() -> None:
    """The knobs default to broad-language-ready 'eng' and psm 3 (automatic page segmentation)."""
    config = OcrTesseractConfig()
    assert config.lang == "eng"
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
    """_read passes the config's lang/psm to the engine and folds its data into text + score."""
    captured: dict = {}

    async def _fake_read(image: bytes, lang: str, psm: int) -> dict:
        captured["image"] = image
        captured["lang"] = lang
        captured["psm"] = psm
        return {"text": ["hello", "world"], "conf": [80.0, 60.0]}

    monkeypatch.setattr(TesseractEngine, "read", _fake_read)
    node = OcrTesseractNode(id="o", config=OcrTesseractConfig(lang="eng+fra", psm=6))
    figure = FigureItem(block_id="f1", image=b"\x89PNG...")
    result = asyncio.run(node.run(OcrConsumes(figure=figure)))

    # 1. The crop bytes + the config knobs reach the engine.
    assert captured["image"] == b"\x89PNG..."
    assert captured["lang"] == "eng+fra"
    assert captured["psm"] == 6

    # 2. The engine's data folds into the figure's read_text + the normalized confidence score.
    assert result.figure.read_text == "hello world"
    assert result.score == pytest.approx(0.70)  # mean(80, 60) / 100
    assert figure.read_text == ""  # the input item was NOT mutated (copy relay)


def test_read_degrades_to_empty_on_a_blank_crop(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreadable crop (Tesseract finds nothing) yields a score-0 reading rather than crashing."""

    async def _fake_read(image: bytes, lang: str, psm: int) -> dict:
        return {"text": [""], "conf": [-1.0]}

    monkeypatch.setattr(TesseractEngine, "read", _fake_read)
    node = OcrTesseractNode(id="o", config=OcrTesseractConfig())
    result = asyncio.run(node.run(OcrConsumes(figure=FigureItem(block_id="f1", image=b"png"))))
    assert result.figure.read_text == ""
    assert result.score == 0.0
