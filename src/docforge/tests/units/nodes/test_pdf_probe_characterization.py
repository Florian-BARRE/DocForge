# ====== Code Summary ======
# Characterization tests of the PDF handling that rides on pypdf: what PdfProbeNode returns (page
# count) or raises (clear ValueError messages) for real PDFs, plus the pypdf-level facts the probe
# is built on (encryption, text-layer vs scanned, metadata). The expected values were recorded on
# pypdf 6.21.4 and pinned BEFORE the 7.0.0 bump: they must hold, unchanged, on both versions, so a
# future pypdf release that alters this behaviour fails here, not in production.
#
# The fixtures are committed bytes (``fixtures/pdf/``) so the READ path is exercised independently
# of whatever the installed pypdf would WRITE: ``contrat_natif.pdf`` (12 pages, native text, from the
# former corpus), ``text_layer_with_metadata.pdf`` (3 pages, Info dictionary), ``scanned_image_only.pdf``
# (2 image-only pages, no text operators) and three encrypted copies of the 3-page one.
#
# ``cryptography`` is NOT a project dependency, so an AES-encrypted PDF is unreadable here today
# (pypdf raises DependencyError, wrapped as "unreadable PDF"); those cases pin that state. They are
# skipped-by-design when ``cryptography`` happens to be installed (see ``_HAS_CRYPTOGRAPHY``).

# ====== Standard Library Imports ======
import importlib.util
import io
from pathlib import Path

# ====== Third-Party Library Imports ======
import pytest
from pypdf import PdfReader

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.nodes.intake.pdf_probe.core import (
    PdfProbeConfig,
    PdfProbeConsumes,
    PdfProbeNode,
)
from shared_libs.public_models import PdfView

_FIXTURES = Path(__file__).parent / "fixtures" / "pdf"
_HAS_CRYPTOGRAPHY = importlib.util.find_spec("cryptography") is not None


def _read(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


async def _probe(content: bytes, max_pages: int = 2000) -> int:
    """Run the node on raw bytes and return the page count (raises what the node raises)."""
    node = PdfProbeNode(id="pdf_probe", config=PdfProbeConfig(max_pages=max_pages))
    out = await node.run(PdfProbeConsumes(pdf=PdfView(content=content)))
    return out.probe.page_count


# ── PdfProbeNode: readable PDFs ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "pages"),
    [
        ("contrat_natif.pdf", 12),
        ("text_layer_with_metadata.pdf", 3),
        ("scanned_image_only.pdf", 2),
        ("encrypted_empty_user_password_rc4.pdf", 3),  # owner-locked only: empty user password
    ],
)
async def test_probe_counts_the_pages_of_readable_pdfs(name: str, pages: int) -> None:
    assert await _probe(_read(name)) == pages


async def test_probe_tolerates_trailing_junk_after_the_eof_marker() -> None:
    assert await _probe(_read("contrat_natif.pdf") + b"\x00junk" * 50) == 12


async def test_probe_ceiling_message_on_a_real_document() -> None:
    with pytest.raises(ValueError) as excinfo:
        await _probe(_read("contrat_natif.pdf"), max_pages=5)

    assert str(excinfo.value) == "document has 12 pages, exceeds the collection's max_pages=5"


# ── PdfProbeNode: encrypted PDFs ─────────────────────────────────────────────────────────────────


@pytest.mark.skipif(_HAS_CRYPTOGRAPHY, reason="AES needs `cryptography`; absent from the lock")
@pytest.mark.parametrize(
    "name", ["encrypted_empty_user_password_aes256.pdf", "encrypted_user_password_aes256.pdf"]
)
async def test_probe_aes_pdf_is_unreadable_without_the_cryptography_package(name: str) -> None:
    with pytest.raises(ValueError, match=r"^unreadable PDF: cryptography>=.* is required for AES"):
        await _probe(_read(name))


@pytest.mark.skipif(not _HAS_CRYPTOGRAPHY, reason="AES decryption needs `cryptography`")
async def test_probe_aes_pdf_with_empty_user_password_opens_when_cryptography_is_present() -> None:
    assert await _probe(_read("encrypted_empty_user_password_aes256.pdf")) == 3


@pytest.mark.skipif(not _HAS_CRYPTOGRAPHY, reason="AES decryption needs `cryptography`")
async def test_probe_pdf_with_a_user_password_is_rejected_as_password_protected() -> None:
    with pytest.raises(ValueError) as excinfo:
        await _probe(_read("encrypted_user_password_aes256.pdf"))

    assert str(excinfo.value) == "the PDF is password-protected and cannot be read"


# ── PdfProbeNode: corrupt PDFs never leak a traceback ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "content", "reason"),
    [
        ("empty", b"", "Cannot read an empty file"),
        ("garbage", b"this is not a pdf at all" * 20, "Stream has ended unexpectedly"),
        ("header only", b"%PDF-1.7\n", "Stream has ended unexpectedly"),
        ("truncated in half", _read("contrat_natif.pdf")[:39977], "Stream has ended unexpectedly"),
        ("truncated at 95%", _read("contrat_natif.pdf")[:75957], "Stream has ended unexpectedly"),
    ],
)
async def test_probe_wraps_corrupt_pdfs_in_a_clear_value_error(
    label: str, content: bytes, reason: str
) -> None:
    with pytest.raises(ValueError) as excinfo:
        await _probe(content)

    assert str(excinfo.value) == f"unreadable PDF: {reason}", label


# ── pypdf facts the probe relies on: encryption, text layer vs scan, metadata ───────────────────


def _reader(name: str) -> PdfReader:
    return PdfReader(io.BytesIO(_read(name)), strict=False)


def test_native_pdf_has_a_text_layer_and_its_metadata() -> None:
    reader = _reader("contrat_natif.pdf")

    assert not reader.is_encrypted
    assert len(reader.pages) == 12
    assert [len((page.extract_text() or "").strip()) for page in reader.pages] == [
        601, 1688, 2285, 566, 2138, 715, 2158, 1014, 122, 280, 481, 714,
    ]  # fmt: skip
    assert dict(reader.metadata) == {
        "/Author": "python-docx",
        "/CreationDate": "D:20260624080904Z'",
        "/Creator": "Writer",
        "/Producer": "LibreOffice 7.4",
    }
    assert [float(v) for v in reader.pages[0].mediabox] == [0.0, 0.0, 612.0, 792.0]


def test_scanned_pdf_has_images_and_no_text_layer() -> None:
    reader = _reader("scanned_image_only.pdf")

    assert len(reader.pages) == 2
    assert [(page.extract_text() or "").strip() for page in reader.pages] == ["", ""]
    assert [len(page.images) for page in reader.pages] == [1, 1]
    assert reader.metadata is None


def test_text_pdf_exposes_its_text_and_info_dictionary() -> None:
    reader = _reader("text_layer_with_metadata.pdf")

    assert [page.extract_text() for page in reader.pages] == [
        f"Hello page {n} native text layer" for n in (1, 2, 3)
    ]
    assert dict(reader.metadata) == {
        "/Title": "DocForge probe fixture",
        "/Author": "Test Author",
        "/Producer": "hand-built",
        "/Subject": "pypdf 7 characterization",
    }
    assert [len(page.images) for page in reader.pages] == [0, 0, 0]


def test_rc4_pdf_decrypts_with_the_empty_user_password() -> None:
    reader = _reader("encrypted_empty_user_password_rc4.pdf")

    assert reader.is_encrypted
    assert int(reader.decrypt("")) == 1  # PasswordType.USER_PASSWORD
    assert [page.extract_text() for page in reader.pages] == [
        f"Hello page {n} native text layer" for n in (1, 2, 3)
    ]
    assert reader.metadata["/Title"] == "DocForge probe fixture"
