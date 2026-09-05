# ====== Code Summary ======
# Unit tests for InputValidator — the paddle-free client-error gate that rejects an undecodable image
# (/ocr) or PDF (/layout-parsing) as InvalidInputError (-> HTTP 422) BEFORE any inference. Uses real
# Pillow / pypdfium2 (both AVX-free, no PaddlePaddle on the import path), so it runs on this AVX-less
# CPU where PaddlePaddle itself SIGILLs. Proves valid inputs pass and malformed ones raise.

# ====== Standard Library Imports ======
import io

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.validation import InputValidator, InvalidInputError

# A structurally-valid single-page PDF (catalog -> pages -> one empty page). Enough for pypdfium2 to
# parse and count a page without any rendering.
_VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n170\n%%EOF"
)


def _valid_png_bytes() -> bytes:
    """Build a tiny valid PNG in-memory (Pillow is a hard transitive dependency)."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


# ── Image validation ─────────────────────────────────────────────────────────────


def test_verify_image_accepts_a_valid_png() -> None:
    InputValidator.verify_image(_valid_png_bytes())  # must not raise


def test_verify_image_rejects_garbage_bytes() -> None:
    with pytest.raises(InvalidInputError):
        InputValidator.verify_image(b"this is definitely not an image")


def test_verify_image_rejects_an_empty_body() -> None:
    with pytest.raises(InvalidInputError):
        InputValidator.verify_image(b"")


# ── PDF validation ───────────────────────────────────────────────────────────────


def test_verify_pdf_accepts_a_valid_pdf() -> None:
    InputValidator.verify_pdf(_VALID_PDF)  # must not raise


def test_verify_pdf_rejects_garbage_bytes() -> None:
    with pytest.raises(InvalidInputError):
        InputValidator.verify_pdf(b"%PDF but truncated garbage")


def test_verify_pdf_rejects_a_png_sent_as_pdf() -> None:
    with pytest.raises(InvalidInputError):
        InputValidator.verify_pdf(_valid_png_bytes())


# ── Static-only contract ─────────────────────────────────────────────────────────


def test_input_validator_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        InputValidator()
