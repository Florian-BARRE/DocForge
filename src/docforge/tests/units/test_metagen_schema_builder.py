# ====== Code Summary ======
# Unit tests for MetagenSchemaBuilder — the strict JSON-schema generator.
# Covers: the root-object shape (additionalProperties:false, required list), every declared
# field type (string, number, date, bool, enum, string[]), nullable vs required fields,
# the keyword_list defensive alias (via mock spec), unknown-field skip, and the
# OpenAI Structured-Outputs invariants (every key in required, ["T","null"] unions).
#
# NOTE: MetaFieldType = Literal["string","number","date","bool","enum","string[]"].
# "keyword_list" is a defensive alias in the schema builder's _LIST_TYPES but NOT a valid
# MetaFieldType — that case is tested via a MagicMock spec to reach the builder's defensive branch.

from unittest.mock import MagicMock

import pytest

from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec
from common_libs.pipeline.stages.s5b_metagen.schema_builder import MetagenSchemaBuilder


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _spec(
    field_name: str,
    field_type: str = "string",
    required: bool = True,
    enum_values: list[str] | None = None,
) -> MetaFieldSpec:
    """Build a MetaFieldSpec for testing with minimal boilerplate.

    field_type must be a valid MetaFieldType literal.
    """
    return MetaFieldSpec(
        field_name=field_name,
        field_type=field_type,
        required=required,
        enum_values=enum_values,
        origin="generated",
    )


def _mock_spec(field_type: str, required: bool = True) -> MagicMock:
    """Build a MagicMock stand-in for MetaFieldSpec to test defensive branches."""
    spec = MagicMock()
    spec.field_type = field_type
    spec.required = required
    spec.enum_values = None
    return spec


def _target(field_name: str):
    """Minimal target stub — only .field is read by the schema builder."""
    t = MagicMock()
    t.field = field_name
    return t


class TestMetagenSchemaBuilderInstantiation:
    """MetagenSchemaBuilder is static-only; instantiation must be blocked."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            MetagenSchemaBuilder()  # type: ignore[call-arg]


class TestSchemaRootShape:
    """The root schema object must be strict (OpenAI Structured-Outputs safe)."""

    def test_root_is_object(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema([], {})
        assert schema["type"] == "object"

    def test_additional_properties_false(self) -> None:
        """additionalProperties:false is mandatory for OpenAI strict mode."""
        schema = MetagenSchemaBuilder.build_json_schema([], {})
        assert schema["additionalProperties"] is False

    def test_required_is_list(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema([], {})
        assert isinstance(schema["required"], list)

    def test_empty_targets_produces_empty_schema(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema([], {})
        assert schema["properties"] == {}
        assert schema["required"] == []

    def test_every_present_key_in_required(self) -> None:
        """Every resolvable target field must appear in 'required' (OpenAI strict)."""
        targets = [_target("kw"), _target("summary")]
        ft = {"kw": _spec("kw"), "summary": _spec("summary")}
        schema = MetagenSchemaBuilder.build_json_schema(targets, ft)
        assert set(schema["required"]) == {"kw", "summary"}
        assert set(schema["properties"].keys()) == {"kw", "summary"}


class TestScalarTypeMapping:
    """Each scalar field_type maps to the correct JSON schema base type."""

    def test_string_field(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("title")], {"title": _spec("title", "string", required=True)}
        )
        assert schema["properties"]["title"] == {"type": "string"}

    def test_number_field(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("score")], {"score": _spec("score", "number", required=True)}
        )
        assert schema["properties"]["score"] == {"type": "number"}

    def test_bool_field_output_type_is_boolean(self) -> None:
        """MetaFieldType 'bool' maps to JSON schema type 'boolean' (not 'bool')."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("is_technical")], {"is_technical": _spec("is_technical", "bool", required=True)}
        )
        assert schema["properties"]["is_technical"] == {"type": "boolean"}

    def test_date_field_mapped_to_string(self) -> None:
        """date is carried as an ISO string — no format keyword (stripped for strict mode)."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("pub_date")], {"pub_date": _spec("pub_date", "date", required=True)}
        )
        assert schema["properties"]["pub_date"] == {"type": "string"}

    def test_unknown_type_falls_back_to_string(self) -> None:
        """An unrecognised field_type silently falls back to 'string' (builder defensive path).

        MetaFieldSpec only accepts valid MetaFieldType literals, so a spec with an unknown
        type must be constructed via a MagicMock to reach the builder's fallback branch.
        """
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("x")], {"x": _mock_spec("exotic_type")}
        )
        assert schema["properties"]["x"] == {"type": "string"}


class TestEnumMapping:
    """enum fields become constrained strings with an enum list."""

    def test_enum_has_type_string(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("category")],
            {"category": _spec("category", "enum", required=True, enum_values=["a", "b", "c"])},
        )
        prop = schema["properties"]["category"]
        assert prop["type"] == "string"
        assert prop["enum"] == ["a", "b", "c"]

    def test_enum_nullable_uses_type_union(self) -> None:
        """A non-required enum field uses ["string","null"] type union."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("cat")],
            {"cat": _spec("cat", "enum", required=False, enum_values=["x", "y"])},
        )
        prop = schema["properties"]["cat"]
        assert set(prop["type"]) == {"string", "null"}
        assert prop["enum"] == ["x", "y"]

    def test_enum_empty_values_produces_empty_enum_list(self) -> None:
        """An enum field with no declared values emits an empty enum list (edge case)."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("cat")],
            {"cat": _spec("cat", "enum", required=True, enum_values=None)},
        )
        assert schema["properties"]["cat"]["enum"] == []


class TestListTypeMapping:
    """string[] (valid MetaFieldType) and keyword_list (defensive alias) produce array<string>."""

    def test_string_array_type(self) -> None:
        """The canonical 'string[]' MetaFieldType produces an array-of-strings schema."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("authors")], {"authors": _spec("authors", "string[]", required=True)}
        )
        prop = schema["properties"]["authors"]
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "string"}

    def test_keyword_list_defensive_alias(self) -> None:
        """'keyword_list' is a defensive alias in the builder — reaches the same array branch."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("tags")], {"tags": _mock_spec("keyword_list")}
        )
        prop = schema["properties"]["tags"]
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "string"}

    def test_nullable_array_uses_type_union(self) -> None:
        """A non-required string[] field uses ["array","null"] union."""
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("tags")], {"tags": _spec("tags", "string[]", required=False)}
        )
        assert set(schema["properties"]["tags"]["type"]) == {"array", "null"}


class TestNullability:
    """Non-required fields use a type union so the key stays in required (OpenAI strict)."""

    def test_optional_string_uses_union(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("note")], {"note": _spec("note", "string", required=False)}
        )
        prop = schema["properties"]["note"]
        assert isinstance(prop["type"], list)
        assert set(prop["type"]) == {"string", "null"}
        # The key still appears in required (OpenAI strict mode constraint).
        assert "note" in schema["required"]

    def test_optional_number_uses_union(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("score")], {"score": _spec("score", "number", required=False)}
        )
        assert set(schema["properties"]["score"]["type"]) == {"number", "null"}

    def test_optional_bool_uses_union(self) -> None:
        schema = MetagenSchemaBuilder.build_json_schema(
            [_target("flag")], {"flag": _spec("flag", "bool", required=False)}
        )
        assert set(schema["properties"]["flag"]["type"]) == {"boolean", "null"}


class TestUnknownFieldSkip:
    """Targets whose field is absent from field_types are silently skipped."""

    def test_unknown_target_skipped(self) -> None:
        """A target whose field has no entry in field_types is omitted from the schema."""
        targets = [_target("known"), _target("ghost")]
        ft = {"known": _spec("known", "string", required=True)}
        schema = MetagenSchemaBuilder.build_json_schema(targets, ft)
        assert "known" in schema["properties"]
        assert "ghost" not in schema["properties"]
        assert "ghost" not in schema["required"]

    def test_all_unknown_produces_empty_schema(self) -> None:
        targets = [_target("a"), _target("b")]
        schema = MetagenSchemaBuilder.build_json_schema(targets, {})
        assert schema["properties"] == {}
        assert schema["required"] == []


class TestMultipleTargets:
    """Multiple targets with mixed types are encoded in one schema."""

    def test_mixed_types(self) -> None:
        targets = [_target("kw"), _target("score"), _target("tags")]
        ft = {
            "kw": _spec("kw", "string", required=True),
            "score": _spec("score", "number", required=False),
            "tags": _spec("tags", "string[]", required=True),
        }
        schema = MetagenSchemaBuilder.build_json_schema(targets, ft)
        assert schema["properties"]["kw"] == {"type": "string"}
        assert set(schema["properties"]["score"]["type"]) == {"number", "null"}
        assert schema["properties"]["tags"]["type"] == "array"
        assert set(schema["required"]) == {"kw", "score", "tags"}
