# ====== Code Summary ======
# Unit tests for the core InputValidator, built from the PaddleServerConfig exactly as PaddleServer
# does — the paddle-free client-error gate that rejects an undecodable image (/ocr) or PDF
# (/layout-parsing, /vl-parse) as InvalidInputError (-> HTTP 422) BEFORE any inference. paddle_server
# used to carry its own copy of the validator. Uses real Pillow / pypdfium2 (both AVX-free, no PaddlePaddle on the import path), so it runs on this AVX-less
# CPU where PaddlePaddle itself SIGILLs. Proves valid inputs pass and malformed ones raise.

# ====== Third-Party Library Imports ======
import pytest
from model_server_core import InputValidator, InvalidInputError

# ====== Internal Project Imports ======
from config_loader import PaddleServerConfig
from tests.support.paddle_app import VALID_PDF, valid_png_bytes

VALIDATOR = InputValidator.from_config(PaddleServerConfig)


# ── Image validation ─────────────────────────────────────────────────────────────


def test_verify_image_accepts_a_valid_png() -> None:
    VALIDATOR.verify_image(valid_png_bytes())  # must not raise


def test_verify_image_rejects_garbage_bytes() -> None:
    with pytest.raises(InvalidInputError):
        VALIDATOR.verify_image(b"this is definitely not an image")


def test_verify_image_rejects_an_empty_body() -> None:
    with pytest.raises(InvalidInputError):
        VALIDATOR.verify_image(b"")


# ── PDF validation ───────────────────────────────────────────────────────────────


def test_verify_pdf_accepts_a_valid_pdf() -> None:
    VALIDATOR.verify_pdf(VALID_PDF)  # must not raise


def test_verify_pdf_rejects_garbage_bytes() -> None:
    with pytest.raises(InvalidInputError):
        VALIDATOR.verify_pdf(b"%PDF but truncated garbage")


def test_verify_pdf_rejects_a_png_sent_as_pdf() -> None:
    with pytest.raises(InvalidInputError):
        VALIDATOR.verify_pdf(valid_png_bytes())
