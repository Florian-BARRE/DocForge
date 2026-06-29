# ====== Code Summary ======
# Unit tests verifying that AdmissionValidator treats origin="generated" metadata fields
# exactly like system fields — exempt from required-check and type-check — and that a
# caller-supplied value for a generated field is silently ignored instead of triggering
# the unknown-field policy. User and system field behavior must remain unchanged.

from unittest.mock import MagicMock

import pytest

from common_libs.config.admission.validator import AdmissionValidator


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _collection(
    fields: list[MagicMock],
    unknown_field_policy: str = "ignore",
    supported_formats: list[str] | None = None,
    max_file_size_bytes: int = 10 * 1024 * 1024,
) -> MagicMock:
    """
    Build a mock collection accepted by AdmissionValidator.validate.

    Args:
        fields: MetaFieldSpec mocks with field_name, field_type, required, is_system, origin.
        unknown_field_policy: 'ignore' or 'reject'.
        supported_formats: accepted file extensions (defaults to ['pdf']).
        max_file_size_bytes: file-size limit.
    """
    col = MagicMock()
    col.metadata_fields = fields
    col.unknown_field_policy = unknown_field_policy
    col.supported_formats = supported_formats or ["pdf"]
    col.max_file_size_bytes = max_file_size_bytes
    return col


def _field(
    name: str,
    field_type: str = "string",
    required: bool = False,
    is_system: bool = False,
    origin: str = "user",
    enum_values: list[str] | None = None,
) -> MagicMock:
    """Build a MetaFieldSpec mock."""
    f = MagicMock()
    f.field_name = name
    f.field_type = field_type
    f.required = required
    f.is_system = is_system
    f.origin = origin
    f.enum_values = enum_values
    return f


def _codes(issues: list[dict]) -> list[str]:
    return [i["code"] for i in issues]


class TestAdmissionValidatorInstantiation:
    """AdmissionValidator is static-only; instantiation must be blocked."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            AdmissionValidator()  # type: ignore[call-arg]


# ─── Generated-field exemption ─────────────────────────────────────────────────

class TestGeneratedFieldRequiredExemption:
    """origin='generated' fields are not required at upload time."""

    def test_generated_required_field_missing_does_not_raise(self) -> None:
        """A generated field marked required=True must NOT trigger missing_required."""
        col = _collection([
            _field("kw", required=True, origin="generated"),
        ])
        issues = AdmissionValidator.validate_metadata(col, {})
        assert "missing_required" not in _codes(issues)

    def test_generated_field_absent_from_payload_is_clean(self) -> None:
        """Zero issues when a generated field is completely absent from the payload."""
        col = _collection([
            _field("summary", required=False, origin="generated"),
        ])
        issues = AdmissionValidator.validate_metadata(col, {})
        assert issues == []

    def test_multiple_generated_required_all_exempt(self) -> None:
        """Multiple required generated fields — none triggers missing_required."""
        col = _collection([
            _field("kw", required=True, origin="generated"),
            _field("sentiment", required=True, origin="generated"),
        ])
        issues = AdmissionValidator.validate_metadata(col, {})
        assert "missing_required" not in _codes(issues)


class TestGeneratedFieldTypeExemption:
    """origin='generated' fields are not type-checked against uploaded values."""

    def test_wrong_type_for_generated_field_not_flagged(self) -> None:
        """Even if a caller sends a wrong-typed value for a generated field, bad_type is not raised."""
        col = _collection([
            _field("score", field_type="number", origin="generated"),
        ])
        # Sending a string where a number is expected — must be silently ignored
        issues = AdmissionValidator.validate_metadata(col, {"score": "not-a-number"})
        assert "bad_type" not in _codes(issues)

    def test_wrong_enum_value_for_generated_field_not_flagged(self) -> None:
        """A bad enum value for a generated field is not rejected."""
        col = _collection([
            _field("category", field_type="enum", origin="generated", enum_values=["a", "b"]),
        ])
        issues = AdmissionValidator.validate_metadata(col, {"category": "z"})
        assert "bad_enum" not in _codes(issues)


class TestGeneratedFieldUnknownFieldPolicy:
    """A caller-supplied value for a generated field is NOT treated as unknown."""

    def test_generated_value_in_payload_not_unknown_on_reject_policy(self) -> None:
        """Even under unknown_field_policy='reject', a generated-field key is not unknown."""
        col = _collection([
            _field("kw", origin="generated"),
        ], unknown_field_policy="reject")
        # Sending a value for the generated field should not trigger unknown_field
        issues = AdmissionValidator.validate_metadata(col, {"kw": "some-value"})
        assert "unknown_field" not in _codes(issues)

    def test_truly_unknown_field_still_rejected(self) -> None:
        """A key that matches no field at all is still rejected under reject policy."""
        col = _collection([], unknown_field_policy="reject")
        issues = AdmissionValidator.validate_metadata(col, {"alien_key": "x"})
        assert "unknown_field" in _codes(issues)


# ─── System-field behavior unchanged ───────────────────────────────────────────

class TestSystemFieldBehaviorUnchanged:
    """is_system=True fields follow the same exemption logic (regression guard)."""

    def test_system_required_field_missing_not_flagged(self) -> None:
        col = _collection([_field("filename", required=True, is_system=True)])
        issues = AdmissionValidator.validate_metadata(col, {})
        assert "missing_required" not in _codes(issues)

    def test_system_field_value_not_type_checked(self) -> None:
        col = _collection([_field("page_count", field_type="number", is_system=True)])
        issues = AdmissionValidator.validate_metadata(col, {"page_count": "not-a-number"})
        assert "bad_type" not in _codes(issues)


# ─── User-field behavior unchanged ────────────────────────────────────────────

class TestUserFieldBehaviorUnchanged:
    """origin='user' fields keep the existing required/type/enum behavior."""

    def test_user_required_field_missing_is_flagged(self) -> None:
        col = _collection([_field("author", required=True, origin="user")])
        issues = AdmissionValidator.validate_metadata(col, {})
        assert "missing_required" in _codes(issues)
        req = next(i for i in issues if i["code"] == "missing_required")
        assert req["status"] == 422

    def test_user_field_wrong_type_is_flagged(self) -> None:
        col = _collection([_field("count", field_type="number", origin="user")])
        issues = AdmissionValidator.validate_metadata(col, {"count": "not-a-number"})
        assert "bad_type" in _codes(issues)

    def test_user_field_bad_enum_is_flagged(self) -> None:
        col = _collection([
            _field("status", field_type="enum", origin="user", enum_values=["a", "b"])
        ])
        issues = AdmissionValidator.validate_metadata(col, {"status": "z"})
        assert "bad_enum" in _codes(issues)

    def test_user_field_correct_value_no_issue(self) -> None:
        col = _collection([_field("note", field_type="string", origin="user")])
        issues = AdmissionValidator.validate_metadata(col, {"note": "hello"})
        assert issues == []


# ─── Mixed-schema admission ────────────────────────────────────────────────────

class TestMixedSchema:
    """Collections with all three origin types together."""

    def test_only_user_required_fields_checked(self) -> None:
        """In a mixed schema, only user-origin required fields block admission."""
        col = _collection([
            _field("author", required=True, origin="user"),
            _field("filename", required=True, is_system=True),
            _field("kw", required=True, origin="generated"),
        ])
        # Payload has author — the only user-required field
        issues = AdmissionValidator.validate_metadata(col, {"author": "Alice"})
        assert issues == []

    def test_missing_user_field_flagged_in_mixed_schema(self) -> None:
        """Missing user-required field in a mixed schema is still flagged."""
        col = _collection([
            _field("author", required=True, origin="user"),
            _field("kw", required=True, origin="generated"),
        ])
        # Payload empty — author is missing; kw is exempt
        issues = AdmissionValidator.validate_metadata(col, {})
        assert "missing_required" in _codes(issues)
        assert len([i for i in issues if i["code"] == "missing_required"]) == 1

    def test_full_admission_pipeline_with_generated_fields(self) -> None:
        """validate() (format + size + metadata) produces no issues for a valid doc."""
        col = _collection(
            fields=[
                _field("author", required=True, origin="user"),
                _field("kw", required=True, origin="generated"),
            ],
            supported_formats=["pdf"],
            max_file_size_bytes=10_000,
        )
        issues = AdmissionValidator.validate(
            col,
            filename="report.pdf",
            size_bytes=5_000,
            user_meta={"author": "Alice"},  # kw not required from upload
        )
        assert issues == []
