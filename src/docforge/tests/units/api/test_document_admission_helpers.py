"""DocumentAdmissionHelpers.extension_rejection — the anti-garbage gate the upload route layers on
top of the content sniff: a PRESENT-but-foreign filename extension is rejected with a clear message,
while an extensionless upload defers to content-truth. Pure/static — no fastapi_app needed for the
helper import (it pulls in no backend context), but we defer the import behind the fixture to keep
the app/ path registration consistent with the rest of tests/units/api."""


def _reject(filename, formats):
    from backend.routers.documents.helpers import DocumentAdmissionHelpers  # noqa: PLC0415

    return DocumentAdmissionHelpers.extension_rejection(filename, formats)


def test_undeclared_extension_is_rejected_with_a_clear_message(fastapi_app) -> None:
    msg = _reject("badfile.xyz", ["pdf", "html", "md", "txt", "docx"])
    assert msg is not None
    assert "'xyz'" in msg
    assert "not accepted" in msg
    # The allowed extensions are listed so the message is actionable.
    assert "pdf" in msg and "txt" in msg


def test_declared_extension_passes(fastapi_app) -> None:
    assert _reject("report.pdf", ["pdf", "txt"]) is None
    assert _reject("notes.md", ["md", "txt"]) is None
    assert _reject("page.htm", ["html"]) is None  # htm is an html alias


def test_extensionless_upload_defers_to_content_truth(fastapi_app) -> None:
    # No extension to contradict → the helper passes and the content sniff decides downstream.
    assert _reject("README", ["txt"]) is None
    assert _reject("upload", ["pdf"]) is None


def test_case_insensitive_extension(fastapi_app) -> None:
    assert _reject("REPORT.PDF", ["pdf"]) is None
    assert _reject("weird.XYZ", ["pdf", "txt"]) is not None
