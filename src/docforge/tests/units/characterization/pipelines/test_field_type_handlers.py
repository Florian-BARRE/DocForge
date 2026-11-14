# ====== Code Summary ======
# Characterization of the per-FieldType rules (safety net for replacing the FieldType if-chains by one
# handler table). Three entry points are driven over EVERY FieldType member x a shared grid of
# representative inputs (valid, bool-for-int, list of non-str, enum miss, null, out-of-range, huge
# int...), and the EXACT outcome of each cell is pinned in goldens/field_type_handlers.json:
#   - AdmissionHelpers.value_error  -> the error string, or None when valid (x enum whitelists);
#   - StructGenHelpers.coerce       -> the repr of the coerced value, or the exception type raised
#                                      (x enum whitelists);
#   - StructGenHelpers.object_schema -> the JSON-schema fragment each type forces (+ enum/datetime
#                                      instruction suffixes).
# repr() is recorded (not the bare value) so True vs 1 vs 1.0 stay distinguishable. A drifted golden is
# a refactoring decision to review, never a test to fix: regenerate on purpose with
# CHARACTERIZATION_REGENERATE=1 (see support/golden_file.py).

# ====== Standard Library Imports ======
import datetime as dt
from collections.abc import Callable
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.nodes.intake.admission.helpers import AdmissionHelpers
from shared_libs.pipelines.nodes.structgen.base import StructGenHelpers
from shared_libs.public_models import FieldType, MetadataFieldSpec

# ====== Local Project Imports ======
from .support.golden_file import GoldenFile

GOLDEN = GoldenFile("field_type_handlers.json")

# One value per interesting class of input — the labels are the golden's keys (unique, stable).
INPUTS: list[tuple[str, Any]] = [
    ("none", None),
    ("true", True),
    ("false", False),
    ("int_0", 0),
    ("int_1", 1),
    ("int_neg", -5),
    ("int_huge", 10**400),  # float() overflows: not a ValueError/TypeError
    ("float_3_0", 3.0),
    ("float_3_7", 3.7),
    ("float_inf", float("inf")),
    ("float_nan", float("nan")),
    ("str_empty", ""),
    ("str_blank", "  "),
    ("str_abc", "abc"),
    ("str_padded", "  abc  "),
    ("str_true", "true"),
    ("str_false_padded", " False "),
    ("str_yes", "yes"),
    ("str_int", "3"),
    ("str_int_padded", " 42 "),
    ("str_float", "3.7"),
    ("str_float_integral", "4.0"),
    ("str_exp", "1e3"),
    ("str_nan", "nan"),
    ("str_alpha_lower", "alpha"),
    ("str_beta_upper", "BETA"),
    ("str_beta_declared", "beta"),
    ("str_gamma", "gamma"),
    ("str_a", "a"),
    ("str_b", "b"),
    ("str_z_miss", "zzz"),
    ("date_iso", "2024-01-15"),
    ("datetime_iso", "2024-01-15T10:00:00"),
    ("datetime_offset", "2024-01-15T10:00:00+02:00"),
    ("datetime_zulu", "2024-01-15T10:00:00Z"),
    ("datetime_compact", "20240115"),
    ("datetime_padded", "  2024-01-15T10:00:00  "),
    ("datetime_bad_month", "2024-13-45"),
    ("datetime_garbage", "not-a-date"),
    ("py_date", dt.date(2024, 1, 15)),
    ("py_datetime", dt.datetime(2024, 1, 15, 10, 0, 0)),
    ("list_empty", []),
    ("list_str", ["a", "b"]),
    ("list_str_padded", ["  a ", "", "  ", "b"]),
    ("list_str_enum_ok", ["Alpha", "beta"]),
    ("list_str_enum_mixed", ["alpha", "zzz"]),
    ("list_int", [1, 2, 3]),
    ("list_int_neg", [-1, 0]),
    ("list_int_bool", [1, True]),
    ("list_int_float", [1, 2.5, 3.0]),
    ("list_int_str", ["1", "2.5", " 3 ", "x"]),
    ("list_float", [1.5, 2]),
    ("list_float_bool", [1.5, True]),
    ("list_float_str", ["1.5", "bad"]),
    ("list_float_inf_str", ["inf", "nan"]),
    ("list_bool", [True, False]),
    ("list_none", [None]),
    ("list_mixed", ["a", 1]),
    ("list_nested", [["a"]]),
    ("list_huge", [10**400]),
    ("tuple_str", ("a", "b")),
    ("set_str", {"a"}),
    ("dict", {"a": 1}),
    ("bytes", b"abc"),
]

# The enum whitelists the grid is crossed with: absent, empty, mixed-case with a padded member.
ENUMS: dict[str, list[str] | None] = {
    "no_enum": None,
    "empty_enum": [],
    "enum_alpha_beta": ["Alpha", "beta", " Gamma "],
    "enum_a_b": ["a", "b"],
}


def _outcome(call: Callable[[], Any]) -> str:
    """The pinned form of one call: ``ok:<repr>`` or ``raise:<ExceptionType>``."""
    try:
        return f"ok:{call()!r}"
    except Exception as exc:  # noqa: BLE001 — the exception TYPE is the thing under characterization
        return f"raise:{type(exc).__name__}"


def _spec(field_type: FieldType, enum_values: list[str] | None) -> MetadataFieldSpec:
    return MetadataFieldSpec(field_name="f", field_type=field_type, enum_values=enum_values)


@pytest.mark.parametrize("field_type", list(FieldType), ids=lambda t: t.value)
def test_admission_value_error_matches_golden(field_type: FieldType) -> None:
    table = {
        enum_name: {
            label: _outcome(
                lambda v=value: AdmissionHelpers.value_error(_spec(field_type, enums), v)
            )
            for label, value in INPUTS
        }
        for enum_name, enums in ENUMS.items()
    }
    GOLDEN.check(f"admission.{field_type.value}", table)


@pytest.mark.parametrize("field_type", list(FieldType), ids=lambda t: t.value)
def test_structgen_coerce_matches_golden(field_type: FieldType) -> None:
    table = {
        enum_name: {
            label: _outcome(lambda v=value: StructGenHelpers.coerce(v, field_type, enums))
            for label, value in INPUTS
        }
        for enum_name, enums in ENUMS.items()
    }
    GOLDEN.check(f"coerce.{field_type.value}", table)


@pytest.mark.parametrize("field_type", list(FieldType), ids=lambda t: t.value)
def test_structgen_object_schema_matches_golden(field_type: FieldType) -> None:
    schemas = {
        enum_name: _outcome(
            lambda e=enums: StructGenHelpers.object_schema([(_spec(field_type, e), "the field")])
        )
        for enum_name, enums in ENUMS.items()
    }
    GOLDEN.check(f"schema.{field_type.value}", schemas)


def test_golden_covers_every_field_type() -> None:
    """A new FieldType member must get its snapshots (and a handler) before this goes green."""
    import json

    snapshots = json.loads(GOLDEN._path.read_text())  # noqa: SLF001 — the net checks its own file
    for field_type in FieldType:
        for kind in ("admission", "coerce", "schema"):
            assert f"{kind}.{field_type.value}" in snapshots
