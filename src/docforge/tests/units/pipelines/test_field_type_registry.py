# ====== Code Summary ======
# The FieldTypeRegistry contract: every FieldType member has exactly one handler, keyed by its own
# field_type, and a type outside the table is refused (the per-type behaviour itself is pinned by
# tests/units/characterization/pipelines/test_field_type_handlers.py).

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.field_types import FieldTypeHandler, FieldTypeRegistry
from shared_libs.public_models import FieldType


@pytest.mark.parametrize("field_type", list(FieldType), ids=lambda t: t.value)
def test_every_field_type_has_its_own_handler(field_type: FieldType) -> None:
    handler = FieldTypeRegistry.get(field_type)
    assert isinstance(handler, FieldTypeHandler)
    assert handler.field_type == field_type


def test_the_table_has_no_extra_entry() -> None:
    assert set(FieldTypeRegistry.all()) == set(FieldType)


def test_a_non_member_is_refused() -> None:
    with pytest.raises(KeyError):
        FieldTypeRegistry.get("not-a-type")  # type: ignore[arg-type]


def test_the_registry_is_not_instantiable() -> None:
    with pytest.raises(TypeError):
        FieldTypeRegistry()
