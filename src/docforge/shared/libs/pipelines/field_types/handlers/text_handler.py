# ====== Code Summary ======
# TextHandler — the TEXT FieldType: validated and coerced exactly like a string (long free text).

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from .string_handler import StringHandler


class TextHandler(StringHandler):
    """TEXT — long free text; same rules as STRING."""

    field_type = FieldType.TEXT


__all__ = ["TextHandler"]
