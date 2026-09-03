"""B2 — the fully-local figure classifier backend (classify_backend="local").

Proves the classify node classifies with NO hosted VLM call when its backend is ``local``:
  * the geometric fast-paths still fire (full-page crop -> scanned_text, tiny crop -> decorative);
  * the local OCR text-density signal drives scanned_text on dense text;
  * an ambiguous crop degrades to photo with a LOW score;
  * the VLM hook is NEVER invoked (fully offline).
The local OCR signal is injected via the overridable ``_local_signal`` hook, so the test needs no
onnxruntime — the same seam ``_ask_model`` gives the VLM backend.
"""

import struct

from shared_libs.pipelines.ingest.nodes.enrich.figure_classify import (
    FigureClassifyConfig,
    FigureClassifyConsumes,
    FigureClassifyNode,
)
from shared_libs.public_models import FigureItem, FigureKind


def _png(width: int, height: int) -> bytes:
    """A minimal PNG whose IHDR carries (width, height) — enough for png_dimensions."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    return signature + ihdr + b"\x00" * 8


class _LocalProbe(FigureClassifyNode):
    """A local-backend classifier whose OCR signal is injected and whose VLM hook must never fire."""

    KIND = "test_figure_classify_local_probe"
    NAME = "probe"
    SUMMARY = "test"

    # Injected (text, confidence, coverage) — the OCR density signal the local backend classifies on.
    signal: tuple[str, float, float] = ("", 0.0, 0.0)

    async def _ask_model(self, image: bytes, prompt: str) -> str:
        raise AssertionError("the VLM hook must never be called on the local backend")

    async def _local_signal(self, image: bytes) -> tuple[str, float, float]:
        return self.signal


def _node(signal: tuple[str, float, float] = ("", 0.0, 0.0)) -> _LocalProbe:
    node = _LocalProbe(id="c", config=FigureClassifyConfig(classify_backend="local"))
    node.signal = signal
    return node


async def test_full_page_crop_is_scanned_text_via_the_geometric_fast_path() -> None:
    """A crop covering most of the page is a scan — decided for free, no OCR, no VLM."""
    node = _node()
    figure = FigureItem(block_id="f", image=_png(1000, 1400), page_coverage=0.95)
    out = await node.run(FigureClassifyConsumes(figure=figure))
    assert out.kind == FigureKind.SCANNED_TEXT.value
    assert out.score >= 0.85


async def test_tiny_crop_is_decorative_via_the_geometric_fast_path() -> None:
    """A tiny crop (logo/rule/bullet) is decorative — decided for free, no OCR, no VLM."""
    node = _node()
    figure = FigureItem(block_id="f", image=_png(20, 20), page_coverage=0.02)
    out = await node.run(FigureClassifyConsumes(figure=figure))
    assert out.kind == FigureKind.DECORATIVE.value


async def test_dense_text_is_scanned_text_via_the_local_ocr_density_signal() -> None:
    """A non-full-page crop with dense, confident OCR text classifies as scanned_text locally."""
    node = _node(signal=("a lot of read text here", 0.9, 0.6))
    figure = FigureItem(block_id="f", image=_png(600, 400), page_coverage=0.3)
    out = await node.run(FigureClassifyConsumes(figure=figure))
    assert out.kind == FigureKind.SCANNED_TEXT.value
    assert 0.0 < out.score <= 1.0


async def test_ambiguous_crop_degrades_to_photo_with_a_low_score() -> None:
    """No text and no decisive visual signal → a safe photo at a LOW score (a ScoreBelow can escalate)."""
    node = _node(signal=("", 0.0, 0.0))
    figure = FigureItem(block_id="f", image=_png(600, 400), page_coverage=0.3)
    out = await node.run(FigureClassifyConsumes(figure=figure))
    assert out.kind == FigureKind.PHOTO.value
    assert out.score <= 0.4


async def test_local_backend_stamps_a_valid_figure_kind_and_never_calls_the_vlm() -> None:
    """Whatever the crop, the stamped kind is a real FigureKind and the VLM hook stays untouched."""
    node = _node(signal=("sparse", 0.6, 0.05))
    figure = FigureItem(block_id="f", image=_png(600, 400), page_coverage=0.3)
    out = await node.run(FigureClassifyConsumes(figure=figure))
    assert out.kind in {k.value for k in FigureKind}
    # The stamped figure is a COPY carrying the decided kind (the input item is untouched).
    assert out.figure.kind == out.kind
    assert figure.kind == ""


def test_local_backend_config_needs_no_endpoint() -> None:
    """The local backend builds with no base_url / model — fully offline, zero placeholder."""
    config = FigureClassifyConfig(classify_backend="local")
    assert config.base_url == "" and config.model == ""
    assert config.classify_backend == "local"
