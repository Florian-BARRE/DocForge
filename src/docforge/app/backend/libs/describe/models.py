# ====== Code Summary ======
# The collection-guide API contract — the response shape of GET /collections/{id}/describe. A LEAN,
# agent-oriented description of how to query one collection: its fields (meaning, type, flags, real
# example values), the valid `search_in` targets, the filter grammar the search route actually
# accepts, and ready-to-send example search bodies built from the real fields. Deliberately carries
# NO pipeline/search blob and no secret. Pure data models — CollectionDescriber fills them.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType


class FieldGuide(BaseModel):
    """
    One metadata field, described for a client that wants to filter or search on it.

    Attributes:
        name (str): The field name (the key used in ``filters`` / ``search_in``).
        type (FieldType): The declared data type.
        description (str | None): What the field means (None when the schema sets none).
        scope (FieldScope): Where the value lives — one per document, or one per chunk.
        origin (FieldOrigin): Who fills it — user, system or generated.
        filterable (bool): Usable as a ``filters`` key.
        semantic (bool): Searchable on its dense vector (``search_in`` semantic).
        lexical (bool): Searchable on its sparse vector (``search_in`` lexical).
        required (bool): Required at upload.
        enum_values (list[str] | None): The allowed values of an enum field.
        example_values (list[str]): Up to 10 stored values, most frequent first (truncated).
        distinct_count (int): Number of distinct stored values (list items counted individually).
        note (str | None): Why examples are omitted, when they are.
    """

    name: str
    type: FieldType
    description: str | None = None
    scope: FieldScope
    origin: FieldOrigin
    filterable: bool
    semantic: bool
    lexical: bool
    required: bool
    enum_values: list[str] | None = None
    example_values: list[str] = Field(default_factory=list)
    distinct_count: int
    note: str | None = None


class SearchTargetGuide(BaseModel):
    """
    One valid ``search_in`` entry of the collection (exactly what the search route accepts).

    Attributes:
        field (str): ``"content"`` (the chunk body) or a metadata field name.
        semantic (bool): The field has a dense vector to query.
        lexical (bool): The field has a sparse vector to query.
    """

    field: str
    semantic: bool
    lexical: bool


class CollectionDescription(BaseModel):
    """
    The lean agent guide to one collection — what is in it and how to query it.

    Attributes:
        collection_id (uuid.UUID): The collection id.
        name (str): The collection name.
        document_count (int): Number of documents in the collection.
        title_field (str | None): The document-scope field used as each hit's display title.
        page_numbering (str): How hits locate pages (which field to cite).
        fields (list[FieldGuide]): Every metadata field of the schema.
        searchable_targets (list[SearchTargetGuide]): The valid ``search_in`` entries.
        filter_grammar (list[str]): The filter value forms the search route accepts.
        example_requests (list[dict]): Ready-to-send search request bodies for this collection.
    """

    collection_id: uuid.UUID
    name: str
    document_count: int
    title_field: str | None = None
    page_numbering: str
    fields: list[FieldGuide]
    searchable_targets: list[SearchTargetGuide]
    filter_grammar: list[str]
    example_requests: list[dict[str, Any]]


__all__ = ["FieldGuide", "SearchTargetGuide", "CollectionDescription"]
