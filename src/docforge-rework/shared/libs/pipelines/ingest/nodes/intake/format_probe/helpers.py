# ====== Code Summary ======
# FormatProbeHelpers — deterministic content sniffing for the formats DocForge ingests: byte signatures
# (PDF, PNG, JPEG), zip-container inspection for OOXML/ODF (docx/xlsx/pptx/odt), an HTML sniff, and
# a UTF-8 text fallback (md by extension). Explicit rules over a magic library: every decision is
# readable and testable. Pure functions — no I/O.

# ====== Standard Library Imports ======
import io
import zipfile


class FormatProbeHelpers:
    """Static content-detection rules — pure, no side effects."""

    # Detected format token → MIME type.
    MIME_TYPES: dict[str, str] = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "odt": "application/vnd.oasis.opendocument.text",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "odp": "application/vnd.oasis.opendocument.presentation",
        "doc": "application/msword",
        "xls": "application/vnd.ms-excel",
        "ppt": "application/vnd.ms-powerpoint",
        "rtf": "application/rtf",
        "csv": "text/csv",
        "html": "text/html",
        "md": "text/markdown",
        "txt": "text/plain",
        "png": "image/png",
        "jpeg": "image/jpeg",
        "unknown": "application/octet-stream",
    }

    # OLE2/CFB container magic (legacy Office: doc, xls, ppt).
    OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    # ODF mimetype entry → format token.
    ODF_MIMETYPES: dict[str, str] = {
        "application/vnd.oasis.opendocument.text": "odt",
        "application/vnd.oasis.opendocument.spreadsheet": "ods",
        "application/vnd.oasis.opendocument.presentation": "odp",
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("FormatProbeHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def __zip_format(cls, content: bytes) -> str:
        """Classify a zip container by its member names (OOXML) or mimetype entry (ODF)."""
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
                if any(name.startswith("word/") for name in names):
                    return "docx"
                if any(name.startswith("xl/") for name in names):
                    return "xlsx"
                if any(name.startswith("ppt/") for name in names):
                    return "pptx"
                if "mimetype" in names:
                    declared = archive.read("mimetype").decode("ascii", errors="replace")
                    return cls.ODF_MIMETYPES.get(declared, "unknown")
        except zipfile.BadZipFile:
            pass
        return "unknown"

    @staticmethod
    def __ole_format(content: bytes) -> str:
        """Classify a legacy OLE2 container by its mandatory stream name (stored UTF-16LE)."""
        # The spec-mandated stream names appear UTF-16LE-encoded in the directory sectors, so a
        # raw byte search is a reliable, dependency-free discriminator.
        if "WordDocument".encode("utf-16-le") in content:
            return "doc"
        if "PowerPoint Document".encode("utf-16-le") in content:
            return "ppt"
        if "Workbook".encode("utf-16-le") in content or "Book".encode("utf-16-le") in content:
            return "xls"
        return "unknown"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> tuple[str, str]:
        """
        Detect what the bytes really are.

        Args:
            content (bytes): The raw uploaded bytes.
            filename (str): Only used to tell markdown from plain text.

        Returns:
            tuple[str, str]: (format token, MIME type).
        """
        # 1. Byte signatures.
        if content.startswith(b"%PDF-"):
            return "pdf", cls.MIME_TYPES["pdf"]
        if content.startswith(b"\x89PNG"):
            return "png", cls.MIME_TYPES["png"]
        if content.startswith(b"\xff\xd8\xff"):
            return "jpeg", cls.MIME_TYPES["jpeg"]
        if content.startswith(b"{\\rtf"):
            return "rtf", cls.MIME_TYPES["rtf"]

        # 2. Containers: zip (OOXML / ODF) and OLE2 (legacy doc / xls / ppt).
        if content.startswith(b"PK\x03\x04"):
            detected = cls.__zip_format(content)
            return detected, cls.MIME_TYPES[detected]
        if content.startswith(cls.OLE2_MAGIC):
            detected = cls.__ole_format(content)
            return detected, cls.MIME_TYPES[detected]

        # 3. HTML sniff over the head of the file (past a UTF-8 BOM if present).
        body = content[3:] if content.startswith(b"\xef\xbb\xbf") else content
        head = body[:2048].lstrip().lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            return "html", cls.MIME_TYPES["html"]

        # 4. Decodable text (UTF-8, or UTF-16 by BOM) → csv/markdown by extension, else plain text.
        if body.startswith((b"\xff\xfe", b"\xfe\xff")):
            pass  # UTF-16 BOM — text, classified by extension below
        else:
            try:
                body[:4096].decode("utf-8")
            except UnicodeDecodeError:
                return "unknown", cls.MIME_TYPES["unknown"]
        lowered = filename.lower()
        if lowered.endswith(".csv"):
            return "csv", cls.MIME_TYPES["csv"]
        if lowered.endswith(".md"):
            return "md", cls.MIME_TYPES["md"]
        return "txt", cls.MIME_TYPES["txt"]


__all__ = ["FormatProbeHelpers"]
