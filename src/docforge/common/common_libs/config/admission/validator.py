# ====== Code Summary ======
# Admission-gate validation (spec §10.1): does a (document + payload) satisfy a collection's
# contract? Shared domain logic used both by the document ingest endpoint (validate-then-admit)
# and any dry-validation. Checks file format, file size, and the metadata payload against the
# schema (required / type / enum / unknown_field_policy). Page count is intentionally not checked.

# ====== Standard Library Imports ======
from __future__ import annotations

from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class AdmissionValidator:
    """Static admission validator — produces a list of issues (empty = valid)."""

    logger = loggerplusplus.bind(identifier="Admission")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AdmissionValidator is a static-only class.")

    @classmethod
    def validate(
        cls,
        collection: Any,
        filename: str,
        size_bytes: int,
        user_meta: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """
        Validate a document + payload against a collection's admission contract.

        Returns:
            list[dict]: Issues, each ``{code, status, field, message}``. Empty = valid.
        """
        issues: list[dict[str, Any]] = []

        # 1. Format (→ 415)
        ext = Path(filename).suffix.lstrip(".").lower()
        if ext not in (collection.supported_formats or []):
            issues.append({"code": "unsupported_format", "status": 415, "field": "file",
                           "message": f"Format {ext!r} not accepted. Supported: {collection.supported_formats}"})

        # 2. Size (→ 413) — the only size criterion (page count is not checked)
        if size_bytes > collection.max_file_size_bytes:
            issues.append({"code": "file_too_large", "status": 413, "field": "file",
                           "message": f"File size {size_bytes} exceeds limit {collection.max_file_size_bytes} bytes."})

        # 3. Metadata payload vs schema (→ 422)
        issues.extend(cls._validate_metadata(collection, user_meta or {}))
        return issues

    @classmethod
    def validate_metadata(cls, collection: Any, user_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
        """
        Validate only a metadata payload against a collection schema (no format/size check).

        Used by the metadata-update endpoint, where the file is already admitted and only the
        user metadata changes — re-checking format/size would be wrong (the schema could have
        narrowed since ingest, which must not block a metadata edit).

        Args:
            collection (Any): Collection with its metadata_fields loaded.
            user_meta (dict | None): The full (merged) metadata payload to validate.

        Returns:
            list[dict]: Metadata issues, each ``{code, status, field, message}``. Empty = valid.
        """
        return cls._validate_metadata(collection, user_meta or {})

    @classmethod
    def _validate_metadata(cls, collection: Any, user_meta: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate the payload: required / type / enum for user fields + unknown-field policy."""
        issues: list[dict[str, Any]] = []
        fields = {f.field_name: f for f in (collection.metadata_fields or [])}

        # Generated fields (origin="generated") are produced by S5b at ingestion, never uploaded.
        # They are exempt from the required + type/enum checks below exactly like system fields, and
        # remain in ``fields`` so a value a caller mistakenly sends for one is silently ignored
        # rather than rejected by the unknown-field policy. Logged for traceability.
        generated = [n for n, f in fields.items() if getattr(f, "origin", "user") == "generated"]
        if generated:
            cls.logger.debug(
                f"Admission: {len(generated)} generated field(s) exempt from upload checks: {generated}"
            )

        for name, f in fields.items():
            # Skip pipeline-derived (system) and S5b-produced (generated) fields — neither is part
            # of an upload payload, so requiring or type-checking them here would be wrong.
            if f.is_system or getattr(f, "origin", "user") == "generated":
                continue
            if name in user_meta:
                value = user_meta[name]
                if not cls._type_ok(f.field_type, value):
                    issues.append({"code": "bad_type", "status": 422, "field": name,
                                   "message": f"Field {name!r} must be {f.field_type}."})
                elif f.field_type == "enum" and f.enum_values and str(value) not in f.enum_values:
                    issues.append({"code": "bad_enum", "status": 422, "field": name,
                                   "message": f"Field {name!r} must be one of {f.enum_values}."})
            elif f.required:
                issues.append({"code": "missing_required", "status": 422, "field": name,
                               "message": f"Required field {name!r} is missing from the payload."})

        # System and generated fields stay in ``fields``, so a payload key matching one of them is
        # never reported as unknown (generated values are simply produced by S5b, not by the upload).
        unknown = [k for k in user_meta if k not in fields]
        if unknown and collection.unknown_field_policy == "reject":
            issues.append({"code": "unknown_field", "status": 422, "field": ",".join(unknown),
                           "message": f"Unknown metadata fields rejected: {unknown} (unknown_field_policy=reject)."})
        return issues

    @staticmethod
    def _type_ok(field_type: str, value: Any) -> bool:
        """Check a payload value against a declared field type."""
        if field_type in ("string", "date", "enum"):
            return isinstance(value, str)
        if field_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if field_type == "bool":
            return isinstance(value, bool)
        if field_type == "string[]":
            return isinstance(value, list) and all(isinstance(x, str) for x in value)
        return True
