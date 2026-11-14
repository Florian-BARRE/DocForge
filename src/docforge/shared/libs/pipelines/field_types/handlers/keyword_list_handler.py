# ====== Code Summary ======
# KeywordListHandler — the KEYWORD_LIST FieldType (a list of enumerable string tags).

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from .string_list_handler import StringListHandler


class KeywordListHandler(StringListHandler):
    """KEYWORD_LIST — a list of enumerable string tags."""

    field_type = FieldType.KEYWORD_LIST


__all__ = ["KeywordListHandler"]
