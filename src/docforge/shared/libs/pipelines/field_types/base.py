# ====== Code Summary ======
# FieldTypeHandler — the contract of one metadata FieldType: what a declared value must look like
# (admission), how a model-returned value is strictly coerced to it (structgen) and which JSON-schema
# fragment forces the model output. One concrete handler per FieldType (``handlers/``), looked up
# through ``FieldTypeRegistry`` — callers never branch on the FieldType themselves.

# ====== Standard Library Imports ======
from abc import ABC, abstractmethod
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType


class FieldTypeHandler(ABC):
    """The rules of one FieldType — pure, no I/O.

    Subclasses set ``field_type``, ``expectation`` (the end of the admission error message) and
    ``json_schema``, then implement ``accepts`` and ``coerce``.
    """

    field_type: FieldType
    # Completes "field '<name>' must be ..." in the admission error.
    expectation: str
    # The nullable JSON-schema fragment of the type (the model may honestly answer null).
    json_schema: dict[str, Any]

    @abstractmethod
    def accepts(self, value: Any) -> bool:
        """Whether a caller-declared value has the right shape for this type."""

    def value_error(self, field_name: str, value: Any) -> str | None:
        """The admission error for a declared value, or None when its shape is valid."""
        if self.accepts(value):
            return None
        return f"field '{field_name}' must be {self.expectation}"

    @abstractmethod
    def coerce(self, value: Any, enum_values: list[str] | None = None) -> Any | None:
        """Strictly coerce a non-null model value to this type, None when it must be dropped.

        May raise ValueError / TypeError for an uncoercible value (the caller drops it).
        """

    def schema_property(self, instruction: str, enum_values: list[str] | None) -> dict[str, Any]:
        """The structured-output schema property of one field (fragment + its description)."""
        fragment = dict(self.json_schema)
        fragment["description"] = instruction
        return fragment


__all__ = ["FieldTypeHandler"]
