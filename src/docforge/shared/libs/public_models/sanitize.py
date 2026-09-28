# ====== Code Summary ======
# TextSanitizer — the one pure primitive that strips U+0000 (the NUL code point) from any value bound
# for a PostgreSQL text/jsonb column. PostgreSQL is the single Unicode-aware store that CANNOT hold
# U+0000 in a text/jsonb value (asyncpg raises UntranslatableCharacterError at INSERT), yet a NUL is
# never real document content — parsers and providers occasionally leak one from a corrupt PDF text
# layer. Stripping it is always safe. The helper recurses into the list/dict shapes a JSONB column
# stores so a NUL buried inside a metadata list of strings is caught too.

# ====== Standard Library Imports ======
from typing import Any


class TextSanitizer:
    """Static, pure NUL-stripping for values bound for Postgres text/jsonb columns."""

    _NUL = "\x00"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TextSanitizer is a static-only class and cannot be instantiated.")

    @classmethod
    def strip_nul(cls, value: Any) -> Any:
        """
        Remove every U+0000 from a value, recursing through JSONB list/dict shapes.

        Strings are stripped; lists/tuples and dicts are rebuilt with each element/value cleaned
        (dict keys too, since a JSONB object key is also stored as text); any other type is returned
        untouched. The container type is preserved (a list stays a list, a tuple a tuple).

        Args:
            value (Any): A scalar or a nested list/dict/tuple structure (a JSONB value).

        Returns:
            Any: The same shape with all U+0000 code points removed.
        """
        # 1. The scalar case — the only place a NUL can actually live.
        if isinstance(value, str):
            return value.replace(cls._NUL, "") if cls._NUL in value else value
        # 2. Ordered sequences — clean each element, preserving list vs tuple.
        if isinstance(value, list):
            return [cls.strip_nul(item) for item in value]
        if isinstance(value, tuple):
            return tuple(cls.strip_nul(item) for item in value)
        # 3. Mappings — a JSONB object stores its keys as text too, so clean both sides.
        if isinstance(value, dict):
            return {cls.strip_nul(key): cls.strip_nul(item) for key, item in value.items()}
        # 4. Anything else (int/float/bool/None/bytes) cannot carry a NUL text escape — pass through.
        return value


__all__ = ["TextSanitizer"]
