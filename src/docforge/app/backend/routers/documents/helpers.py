# ====== Code Summary ======
# DocumentAdmissionHelpers — the pure, store-free checks the upload route layers on top of the
# content sniff. Content-truth (the detected format must be in the collection's accepted set) is the
# anti-spoofing gate; this adds the complementary anti-garbage gate: a file whose filename carries a
# PRESENT-but-foreign extension (e.g. ``badfile.xyz``) is rejected with a clear, human message
# instead of being silently bucketed as ``txt`` by the decodable-text fallback. An extensionless
# upload is left to content-truth (there is no claimed extension to contradict), so paste/streamed
# uploads keep working. The two gates compose — both must pass — so neither can mask the other.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from pathlib import PurePosixPath

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class DocumentAdmissionHelpers:
    """Static upload-admission checks that complement the content sniff (pure, no I/O)."""

    logger = loggerplusplus.bind(identifier="DocumentAdmissionHelpers")

    # Accepted-format token → the filename extensions that legitimately carry it. Aligned with the
    # tokens FormatProbeHelpers emits; a collection's accepted-extension set is the union over its
    # supported_formats. Extension-detection is a sanity check ONLY — the format itself is always
    # decided by the content sniff (a ``.pdf`` holding HTML is still caught by content-truth).
    _FORMAT_EXTENSIONS: dict[str, frozenset[str]] = {
        "pdf": frozenset({"pdf"}),
        "docx": frozenset({"docx"}),
        "doc": frozenset({"doc"}),
        "xlsx": frozenset({"xlsx"}),
        "xls": frozenset({"xls"}),
        "pptx": frozenset({"pptx"}),
        "ppt": frozenset({"ppt"}),
        "odt": frozenset({"odt"}),
        "ods": frozenset({"ods"}),
        "odp": frozenset({"odp"}),
        "rtf": frozenset({"rtf"}),
        "csv": frozenset({"csv"}),
        "html": frozenset({"html", "htm"}),
        "md": frozenset({"md", "markdown"}),
        "txt": frozenset({"txt", "text"}),
        "png": frozenset({"png"}),
        "jpeg": frozenset({"jpg", "jpeg"}),
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "DocumentAdmissionHelpers is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def _extension(filename: str) -> str:
        """The lowercase extension of a filename, without the dot ('' when absent)."""
        # Mirror the pipeline admit node's extraction so both gates read the extension identically.
        return PurePosixPath(filename.replace("\\", "/")).suffix.lstrip(".").lower()

    @classmethod
    def accepted_extensions(cls, supported_formats: Sequence[str]) -> set[str]:
        """
        The set of filename extensions the collection's accepted formats legitimately carry.

        Args:
            supported_formats (Sequence[str]): The collection's accepted format tokens.

        Returns:
            set[str]: Every extension (lowercase, no dot) associated with an accepted format.
        """
        # 1. Union the per-format extension sets; an unmapped format contributes nothing.
        extensions: set[str] = set()
        for fmt in supported_formats:
            extensions |= cls._FORMAT_EXTENSIONS.get(fmt, frozenset())
        return extensions

    @classmethod
    def extension_rejection(cls, filename: str, supported_formats: Sequence[str]) -> str | None:
        """
        Reject a PRESENT-but-undeclared filename extension, or pass (None) when it is acceptable.

        Complements the content sniff: it fires only when the file HAS an extension that no accepted
        format carries (the ``badfile.xyz`` case). An extensionless filename returns None so
        content-truth alone decides — there is no claimed extension to contradict.

        Args:
            filename (str): The uploaded filename (may be extensionless).
            supported_formats (Sequence[str]): The collection's accepted format tokens.

        Returns:
            str | None: A human-readable rejection message, or None when the extension is acceptable
                (or absent).
        """
        # 1. No extension → nothing to contradict; defer entirely to the content sniff.
        ext = cls._extension(filename)
        if not ext:
            return None
        # 2. A present extension must belong to an accepted format, else it is a clear rejection.
        accepted = cls.accepted_extensions(supported_formats)
        if ext in accepted:
            return None
        return (
            f"file extension '{ext}' is not accepted for this collection "
            f"(allowed: {sorted(accepted)})"
        )


__all__ = ["DocumentAdmissionHelpers"]
