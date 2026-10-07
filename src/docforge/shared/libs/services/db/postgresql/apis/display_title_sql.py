# ====== Code Summary ======
# DisplayTitleSql — the document grid's DISPLAY-title expression in SQL: the collection's title_field
# value over the parsed title, the same rule as DisplayTitleResolver. The value is read through ONE
# LEFT OUTER JOIN on the unique (document_id, field_id) row rather than a correlated scalar subquery:
# a per-row subquery inflates the plan cost past Postgres' JIT threshold on ~10k+ documents and
# JIT-compiles every grid page (measured 436 ms vs 73 ms on 50k documents).

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import Select, and_, case, func, literal, literal_column, select
from sqlalchemy.orm import aliased

# ====== Local Project Imports ======
from ..tables import Document, DocumentMetadata

# The separator a list-typed title_field value is rendered with (mirrors DisplayTitleResolver).
_TITLE_LIST_SEPARATOR = ", "
# The characters Python's str.strip() removes for ASCII text — btrim() alone strips only spaces, so a
# whitespace-only value would otherwise render as a title in SQL but fall back in Python.
_WHITESPACE = " \t\n\r\f\v"

# The aliased metadata row carrying a document's title_field value (joined at most once per statement).
_TITLE_META = aliased(DocumentMetadata, name="title_meta")


class DisplayTitleSql:
    """Static builder of the display-title join + expression for the document grid statements."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DisplayTitleSql is a static-only class and cannot be instantiated.")

    @staticmethod
    def _trim(expression: Any) -> Any:
        """``btrim`` over every ASCII whitespace character, matching Python's ``str.strip()``."""
        return func.btrim(expression, literal(_WHITESPACE))

    @classmethod
    def _rendered_value(cls) -> Any:
        """The joined JSONB value rendered as Python's ``str()`` would (list joined, bool as True)."""
        # 1. A list joins its non-blank trimmed elements with ", " (only arrays reach this branch).
        value = _TITLE_META.value
        element = (
            func.jsonb_array_elements_text(value)
            .table_valued("item")
            .render_derived(name="title_item")
        )
        joined = (
            select(func.string_agg(cls._trim(element.c.item), literal(_TITLE_LIST_SEPARATOR)))
            .select_from(element)
            .where(cls._trim(element.c.item) != "")
            .scalar_subquery()
        )
        # 2. A boolean renders capitalised like Python; any other scalar is its unquoted text.
        as_text = value.op("#>>")(literal_column("'{}'"))
        return case(
            (func.jsonb_typeof(value) == "array", joined),
            (func.jsonb_typeof(value) == "boolean", func.initcap(as_text)),
            else_=as_text,
        )

    @classmethod
    def key(cls, title_field_id: int | None) -> Any:
        """
        The display-title expression the title filter + title sort run on.

        Args:
            title_field_id (int | None): The collection's resolved document-scope title field id.

        Returns:
            Any: ``document.title`` without a title field; otherwise the trimmed joined value, falling
            back to ``document.title`` when absent or blank. Requires :meth:`join` on the statement.
        """
        # 1. No title field → the parsed title column itself (index-friendly, no join needed).
        if title_field_id is None:
            return Document.title
        # 2. Blank or absent (no joined row → NULL) → the parsed title, exactly like the resolver.
        return func.coalesce(func.nullif(cls._trim(cls._rendered_value()), ""), Document.title)

    @staticmethod
    def join(statement: Select, title_field_id: int | None) -> Select:
        """
        LEFT OUTER JOIN the title_field value row onto a ``document`` statement (no-op without one).

        Args:
            statement (Select): A statement selecting from ``document``.
            title_field_id (int | None): The collection's resolved document-scope title field id.

        Returns:
            Select: The statement, joined when a title field is configured. The join is on the unique
            ``(document_id, field_id)`` key, so it never multiplies rows.
        """
        if title_field_id is None:
            return statement
        return statement.outerjoin(
            _TITLE_META,
            and_(
                _TITLE_META.document_id == Document.id,
                _TITLE_META.field_id == title_field_id,
            ),
        )


__all__ = ["DisplayTitleSql"]
