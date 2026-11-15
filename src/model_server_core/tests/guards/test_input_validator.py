# ====== Code Summary ======
# Behaviour of InputValidator: empty / oversize / undecodable bodies are InvalidInputError (the 422),
# decoders are looked up by media kind, wiring mistakes are loud, and the size cap comes from the config.

# ====== Standard Library Imports ======
import sys

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from model_server_core import (
    ImageDecoder,
    InputValidator,
    InvalidInputError,
    MediaKind,
    PdfDecoder,
    ServerConfig,
)
from support.fakes.fake_media_decoder import FakeMediaDecoder


def test_a_decodable_body_passes_and_reaches_the_decoder() -> None:
    pdf = FakeMediaDecoder(MediaKind.PDF)
    validator = InputValidator(max_bytes=100, decoders=[pdf])

    validator.validate(MediaKind.PDF, b"%PDF-1.7")

    assert pdf.seen == [b"%PDF-1.7"]


def test_the_decoder_is_chosen_by_media_kind() -> None:
    image, pdf = FakeMediaDecoder(MediaKind.IMAGE), FakeMediaDecoder(MediaKind.PDF)
    validator = InputValidator(max_bytes=100, decoders=[image, pdf])

    validator.verify_image(b"img")
    validator.verify_pdf(b"pdf")

    assert image.seen == [b"img"]
    assert pdf.seen == [b"pdf"]


def test_an_undecodable_body_is_an_invalid_input() -> None:
    validator = InputValidator(
        max_bytes=100, decoders=[FakeMediaDecoder(MediaKind.PDF, reject=True)]
    )

    with pytest.raises(InvalidInputError, match="not a decodable pdf"):
        validator.verify_pdf(b"garbage")


def test_an_empty_body_is_rejected_before_the_decoder() -> None:
    pdf = FakeMediaDecoder(MediaKind.PDF)
    validator = InputValidator(max_bytes=100, decoders=[pdf])

    with pytest.raises(InvalidInputError, match="empty"):
        validator.verify_pdf(b"")
    assert pdf.seen == []


def test_an_oversize_body_is_rejected_before_the_decoder() -> None:
    pdf = FakeMediaDecoder(MediaKind.PDF)
    validator = InputValidator(max_bytes=4, decoders=[pdf])

    with pytest.raises(InvalidInputError, match="4-byte limit"):
        validator.verify_pdf(b"12345")
    assert pdf.seen == []


def test_a_kind_without_decoder_is_a_loud_wiring_error() -> None:
    validator = InputValidator(max_bytes=100, decoders=[FakeMediaDecoder(MediaKind.PDF)])

    with pytest.raises(LookupError, match="image"):
        validator.verify_image(b"img")


def test_two_decoders_for_one_kind_are_refused() -> None:
    with pytest.raises(ValueError, match="two decoders"):
        InputValidator(
            max_bytes=100,
            decoders=[FakeMediaDecoder(MediaKind.PDF), FakeMediaDecoder(MediaKind.PDF)],
        )


def test_a_non_positive_cap_is_refused() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        InputValidator(max_bytes=0, decoders=[])


def test_from_config_takes_the_cap_from_the_server_config_and_defaults_to_image_and_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pillow / pypdfium2 are optional: block them so the test does not depend on the environment.
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    config = type("CappedConfig", (ServerConfig,), {"MAX_BODY_BYTES": 321})

    validator = InputValidator.from_config(config)

    assert validator.max_bytes == 321
    # Both default decoders are registered: the failure is the lazy, optional library, not the lookup.
    with pytest.raises(ImportError):
        validator.verify_image(b"img")
    with pytest.raises(ImportError):
        validator.verify_pdf(b"pdf")


def test_from_config_accepts_explicit_decoders() -> None:
    config = type("CappedConfig", (ServerConfig,), {"MAX_BODY_BYTES": 50})
    pdf = FakeMediaDecoder(MediaKind.PDF)

    InputValidator.from_config(config, [pdf]).verify_pdf(b"x")

    assert pdf.seen == [b"x"]


def test_default_decoders_declare_their_kind() -> None:
    assert ImageDecoder().kind is MediaKind.IMAGE
    assert PdfDecoder().kind is MediaKind.PDF
