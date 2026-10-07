# ====== Code Summary ======
# DisplayTitleResolver — the single rule deciding which title a document shows to readers (search hits,
# document lists, agents). A collection may name one of its document-scope metadata fields as its
# `title_field`; when that field holds a value it IS the document's title (the parser's own title is
# often just the first heading, e.g. "1 GÉNÉRALITÉS"). Otherwise the parser title stays. Pure, no I/O,
# read-time only — no re-ingest is ever needed to change which title is displayed.

# ====== Standard Library Imports ======
from collections.abc import Mapping
from typing import Any


class DisplayTitleResolver:
    """Static, pure resolution of a document's display title."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DisplayTitleResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve(
        parsed_title: str | None, metadata: Mapping[str, Any], title_field: str | None
    ) -> str | None:
        """
        Return the title a document should display.

        Args:
            parsed_title (str | None): The parser-derived title stored on the document row.
            metadata (Mapping[str, Any]): The document's metadata values keyed by field name.
            title_field (str | None): The collection's configured title field, if any.

        Returns:
            str | None: The title_field value when configured and non-empty, else the parsed title.
        """
        # 1. No configured title field → the parser title is all there is.
        if not title_field:
            return parsed_title

        # 2. Render the configured value: a list (e.g. keyword_list) joins, a scalar stringifies.
        value = metadata.get(title_field)
        if isinstance(value, list | tuple):
            rendered = ", ".join(str(item).strip() for item in value if str(item).strip())
        elif value is None:
            rendered = ""
        else:
            rendered = str(value).strip()

        # 3. An unset or blank field falls back to the parser title rather than showing nothing.
        return rendered or parsed_title


__all__ = ["DisplayTitleResolver"]
