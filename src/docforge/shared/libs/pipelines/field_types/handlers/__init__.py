# ---------------------- One handler per FieldType ---------------------- #
from .bool_handler import BoolHandler
from .datetime_handler import DatetimeHandler
from .enum_handler import EnumHandler
from .float_handler import FloatHandler
from .float_list_handler import FloatListHandler
from .integer_handler import IntegerHandler
from .integer_list_handler import IntegerListHandler
from .keyword_list_handler import KeywordListHandler
from .string_handler import StringHandler
from .text_handler import TextHandler
from .text_list_handler import TextListHandler

# Every concrete handler class; the registry instantiates and indexes them by FieldType.
ALL_HANDLERS = (
    StringHandler,
    IntegerHandler,
    FloatHandler,
    BoolHandler,
    KeywordListHandler,
    DatetimeHandler,
    EnumHandler,
    TextHandler,
    IntegerListHandler,
    FloatListHandler,
    TextListHandler,
)

# ------------------- Public API ------------------- #
__all__ = [
    "ALL_HANDLERS",
    "BoolHandler",
    "DatetimeHandler",
    "EnumHandler",
    "FloatHandler",
    "FloatListHandler",
    "IntegerHandler",
    "IntegerListHandler",
    "KeywordListHandler",
    "StringHandler",
    "TextHandler",
    "TextListHandler",
]
