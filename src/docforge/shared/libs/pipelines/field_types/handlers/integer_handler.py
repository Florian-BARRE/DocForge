# ====== Code Summary ======
# IntegerHandler — the INTEGER FieldType: a real int (a bool is not one); coercion keeps only integral values.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class IntegerHandler(FieldTypeHandler):
    """INTEGER — a whole number."""

    field_type = FieldType.INTEGER
    expectation = "an integer"
    json_schema = {"type": ["integer", "null"]}

    @staticmethod
    def as_int(value: Any) -> int | None:
        """
        Coerce a numeric or numeric-string value to an int, only when it is integral.

        A fractional value (3.7 or "3.7") is DROPPED rather than silently truncated, matching the
        string path (where "3.7" already raises and drops) so an INTEGER field never stores a
        rounded-off number the model did not mean.

        Args:
            value (Any): The raw numeric or string value.

        Returns:
            int | None: The integral value, or None when it is fractional.

        Raises:
            ValueError: When the value is not numeric at all.
            TypeError: When the value has no numeric interpretation.
        """
        number = float(value)
        return int(number) if number.is_integer() else None

    def accepts(self, value: Any) -> bool:
        # bool is an int subclass, so exclude it.
        return not isinstance(value, bool) and isinstance(value, int)

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> int | None:
        return None if isinstance(value, bool) else self.as_int(value)


__all__ = ["IntegerHandler"]
