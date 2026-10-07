# ====== Code Summary ======
# SearchGuide — the static half of the collection guide: which `search_in` targets the collection
# accepts (content on both axes + every metadata field on the axes its flags index) and the filter
# grammar the search route really implements today (see qdrant/vectors/filters.py + the search route's
# filterability / range gates). Pure — no I/O. Keep FILTER_GRAMMAR in step with the search route.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Local Project Imports ======
from .models import FieldGuide, SearchTargetGuide

# The chunk-body target — always indexed on both the dense and the sparse axis.
CONTENT_FIELD = "content"

# One line per filter form the search route accepts (filters = {field: value}, fields ANDed).
FILTER_GRAMMAR: tuple[str, ...] = (
    "Only filterable fields may be filtered; several fields are ANDed.",
    '{"field": "v"} equality — string/enum/keyword_list values match case-insensitively.',
    '{"field": ["a", "b"]} any-of (keyword_list: overlap); max 100 values.',
    'Operator form {"field": {"<op>": value}} — ONE operator per field (only range bounds combine):',
    '  "eq": v | "in": [..] — same as the bare forms.',
    '  "not": v | "not_in": [..] — exclude; string values exclude every stored case variant.',
    '  "contains": "sub" | "prefix": "pre" — string/enum/keyword_list: case-insensitive match against '
    "the stored values (>500 matching values → 422, narrow it; none → empty result + hint). "
    'text/text_list: "contains" = full-text match; no "prefix".',
    '  "exists": true|false — the field has a value / is absent, null or empty.',
    '  "gte"/"gt"/"lte"/"lt" — range on integer/float/datetime fields only; datetime bounds are '
    "ISO-8601 strings.",
    "Allowed operators by type: string/enum/keyword_list eq,in,not,not_in,contains,prefix,exists · "
    "text/text_list eq,in,not,not_in,contains,exists · integer eq,in,not,not_in,exists,ranges · "
    "float/datetime exists,ranges · bool eq,not,exists. Anything else → 422 listing the valid ones.",
    "Operator values must have the field's type (integer → numbers, bool → true/false, string → "
    "text); a mistyped value → 422.",
    'text/text_list fields: {"field": "words"} full-text match (all words present); a list = any-of.',
    "A value no document stores returns a hint with the closest stored values.",
)


class SearchGuide:
    """Pure helpers describing what the search route accepts for one collection's schema."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a namespace of pure helpers."""
        raise TypeError(f"{cls.__name__} is a static namespace and cannot be instantiated.")

    @staticmethod
    def targets(fields: Sequence[FieldGuide]) -> list[SearchTargetGuide]:
        """
        List the valid ``search_in`` entries — content first, then each vector-indexed field.

        Args:
            fields (Sequence[FieldGuide]): The collection's described fields.

        Returns:
            list[SearchTargetGuide]: One entry per searchable field with the axes it is indexed on.
        """
        # 1. Content is always searchable on both axes.
        targets = [SearchTargetGuide(field=CONTENT_FIELD, semantic=True, lexical=True)]

        # 2. A metadata field is a target only on the axes its flags index.
        targets += [
            SearchTargetGuide(field=field.name, semantic=field.semantic, lexical=field.lexical)
            for field in fields
            if field.semantic or field.lexical
        ]
        return targets

    @staticmethod
    def filter_grammar() -> list[str]:
        """
        Return the filter grammar lines.

        Returns:
            list[str]: One short line per accepted filter form.
        """
        # 1. A fresh list — callers may not mutate the shared constant.
        return list(FILTER_GRAMMAR)


__all__ = ["SearchGuide", "CONTENT_FIELD"]
