# ====== Code Summary ======
# Regenerates the two binary fixtures of the conversion corpus that have no counterpart under
# tests/units/nodes/fixtures/pdf: a tiny .docx (hand-zipped, stdlib only, so Gotenberg/LibreOffice
# has a real Office document to convert) and a tiny .png (Pillow's bundled bitmap font, so the
# image path has a few words to read). Run only when a fixture must change — a changed fixture
# invalidates the committed snapshot (re-record it, see conversion_corpus/README.md).
#
#   uv run --with pillow python tests/live/fixtures/build_fixtures.py

# ====== Standard Library Imports ======
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)
_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _paragraph(text: str, style: str | None = None) -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


def _cell(text: str) -> str:
    return f"<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"


def _table(rows: list[list[str]]) -> str:
    body = "".join(f"<w:tr>{''.join(_cell(c) for c in row)}</w:tr>" for row in rows)
    return (
        "<w:tbl><w:tblPr><w:tblBorders>"
        + "".join(
            f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            for side in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        + f"</w:tblBorders></w:tblPr>{body}</w:tbl>"
    )


def build_docx(path: Path) -> None:
    """Writes a one-page Word document: a title, two paragraphs and a 3x3 table."""
    body = "".join(
        [
            _paragraph("Conversion Smoke Memo", "Title"),
            _paragraph(
                "This memo exists only to exercise the Office to PDF conversion path of the "
                "ingestion pipeline. It contains a title, running text and a small table."
            ),
            _paragraph(
                "Quarterly figures are listed below. Every cell is plain text so that a change in "
                "table extraction shows up as a change in the document fingerprint."
            ),
            _table([["Region", "Q1", "Q2"], ["North", "120", "135"], ["South", "98", "110"]]),
            _paragraph("End of memo."),
        ]
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_NS}><w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        # Fixed timestamps keep the bytes (hence the content hash) reproducible.
        for name, data in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _ROOT_RELS),
            ("word/document.xml", document),
        ):
            archive.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), data)


def build_png(path: Path) -> None:
    """Writes a 480x160 PNG with three lines of black text on white."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (480, 160), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    for index, line in enumerate(
        ("DocForge image smoke", "Invoice 2026-001", "Total due: 42.00 EUR")
    ):
        draw.text((16, 12 + index * 48), line, fill="black", font=font)
    image.save(path, format="PNG", optimize=False)


if __name__ == "__main__":
    build_docx(HERE / "conversion_memo.docx")
    build_png(HERE / "text_image.png")
