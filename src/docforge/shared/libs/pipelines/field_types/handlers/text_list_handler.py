# ====== Code Summary ======
# TextListHandler — the TEXT_LIST FieldType (a list of free sentences).

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from .string_list_handler import StringListHandler


class TextListHandler(StringListHandler):
    """TEXT_LIST — a list of free sentences (key findings, quotes…)."""

    field_type = FieldType.TEXT_LIST


__all__ = ["TextListHandler"]
