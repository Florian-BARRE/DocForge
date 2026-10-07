# ====== Code Summary ======
# FieldGuideBuilder — describes one metadata field for the collection guide: its schema flags plus a
# bounded sample of its REAL stored values (via the shared MetadataValueResolver). Examples are given
# only where they help a client build a filter — filterable or low-cardinality fields — and never for
# long free text (text / text_list), where a sample would dump paragraphs. Every value is truncated.
# Bounded DB work: one aggregate count + at most one LIMITed grouped read per field.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType
from shared_libs.services.db.facades import MetadataValueResolver
from shared_libs.services.db.postgresql.tables import MetadataField

# ====== Local Project Imports ======
from .models import FieldGuide

# Maximum number of example values sampled per field (most frequent first).
EXAMPLE_LIMIT = 10
# Maximum characters kept of one example value (longer values end with an ellipsis).
VALUE_MAX_CHARS = 80
# A non-filterable field still gets examples when it has at most this many distinct values.
LOW_CARDINALITY = 50
# Free-text types whose values are sentences/paragraphs — never sampled.
FREE_TEXT_TYPES = frozenset({FieldType.TEXT, FieldType.TEXT_LIST})
_FREE_TEXT_NOTE = "Free text, values omitted."
_FREE_TEXT_FILTER_NOTE = " Filter by words: full-text match (all words present)."


class FieldGuideBuilder(LoggerClass):
    """Build the FieldGuide of one metadata field from its schema row + its stored values."""

    def __init__(self, resolver: MetadataValueResolver) -> None:
        """
        Args:
            resolver (MetadataValueResolver): The metadata value oracle (bounded distinct reads).
        """
        LoggerClass.__init__(self)
        self._resolver = resolver

    @staticmethod
    def __free_text_note(field: MetadataField) -> str:
        """Explain the omitted examples (and how to filter, when the field is filterable)."""
        # 1. The filter hint only applies to a filterable field.
        return _FREE_TEXT_NOTE + (_FREE_TEXT_FILTER_NOTE if field.filterable else "")

    async def build(self, field: MetadataField) -> FieldGuide:
        """
        Describe one field: flags, description, distinct count and (when useful) example values.

        Args:
            field (MetadataField): The field's schema row.

        Returns:
            FieldGuide: The field description.
        """
        # 1. One aggregate — the distinct count drives the low-cardinality decision.
        distinct_count = await self._resolver.distinct_count(field)

        # 2. Sample examples only where they help build a filter, never for free text.
        free_text = field.field_type in FREE_TEXT_TYPES
        wants_examples = not free_text and (field.filterable or distinct_count <= LOW_CARDINALITY)
        examples = (
            await self._resolver.distinct_values(field, EXAMPLE_LIMIT)
            if wants_examples and distinct_count
            else []
        )

        # 3. Assemble the guide (every sampled value truncated).
        return FieldGuide(
            name=field.field_name,
            type=field.field_type,
            description=field.description,
            scope=field.scope,
            origin=field.origin,
            filterable=field.filterable,
            semantic=field.semantic,
            lexical=field.lexical,
            required=field.required,
            enum_values=field.enum_values,
            example_values=[self.truncate(value) for value in examples],
            distinct_count=distinct_count,
            note=self.__free_text_note(field) if free_text else None,
        )

    @staticmethod
    def truncate(value: str) -> str:
        """
        Cap a stored value to VALUE_MAX_CHARS characters (an ellipsis marks the cut).

        Args:
            value (str): The stored value.

        Returns:
            str: The value, or its truncated form.
        """
        # 1. Short values pass through; long ones keep their head plus an ellipsis.
        if len(value) <= VALUE_MAX_CHARS:
            return value
        return value[: VALUE_MAX_CHARS - 1] + "…"


__all__ = ["FieldGuideBuilder"]
