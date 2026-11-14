# ====== Code Summary ======
# FieldTypeRegistry — the one table mapping every FieldType to its handler. Built once at import and
# checked complete: a new FieldType member without a handler fails at import (fail-fast), never at the
# first document that uses it.

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from .base import FieldTypeHandler
from .handlers import ALL_HANDLERS


class FieldTypeRegistry:
    """Static lookup FieldType -> FieldTypeHandler."""

    _HANDLERS: dict[FieldType, FieldTypeHandler] = {
        handler.field_type: handler for handler in (cls() for cls in ALL_HANDLERS)
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("FieldTypeRegistry is a static-only class and cannot be instantiated.")

    @classmethod
    def get(cls, field_type: FieldType) -> FieldTypeHandler:
        """The handler of a FieldType (KeyError for anything that is not a registered member)."""
        return cls._HANDLERS[field_type]

    @classmethod
    def all(cls) -> dict[FieldType, FieldTypeHandler]:
        """A copy of the whole table."""
        return dict(cls._HANDLERS)


_missing = set(FieldType) - set(FieldTypeRegistry._HANDLERS)  # noqa: SLF001
if _missing:
    raise RuntimeError(f"FieldTypeRegistry has no handler for: {sorted(_missing)}")

__all__ = ["FieldTypeRegistry"]
