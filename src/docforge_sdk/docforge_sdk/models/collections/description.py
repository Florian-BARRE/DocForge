# ====== Code Summary ======
# Collection description models: the JSON schema of the contract and the self-describing
# guide (fields, search targets) of one collection.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .._shared import FieldOrigin, FieldScope, FieldType


class CollectionContractSchemaResponse(BaseModel):
    """The full discoverable vocabulary of a collection contract — no value has to be guessed."""

    config_schema: dict[str, Any] = Field(
        description="JSON Schema of the collection identity/limits contract (drives the UI form)."
    )
    field_schema: dict[str, Any] = Field(
        description="JSON Schema of one metadata FieldSpec — carries the field_type/origin/scope "
        "enums the identity/limits contract omits."
    )
    supported_format_tokens: list[str] = Field(
        description="Every upload format token a collection may declare in supported_formats "
        "(e.g. 'pdf', 'docx', 'md')."
    )


class FieldGuide(BaseModel):
    """
    One metadata field, described for a client that wants to filter or search on it.

    Attributes:
        name (str): The field name (the key used in ``filters`` / ``search_in``).
        type (FieldType): The declared data type.
        description (str | None): What the field means (None when the schema sets none).
        scope (FieldScope): Where the value lives — one per document, or one per chunk.
        origin (FieldOrigin): Who fills it.
        filterable (bool): Usable as a ``filters`` key.
        semantic (bool): Searchable on its dense vector.
        lexical (bool): Searchable on its sparse vector.
        required (bool): Required at upload.
        enum_values (list[str] | None): The allowed values of an enum field.
        example_values (list[str]): Up to 10 stored values, most frequent first.
        distinct_count (int): Number of distinct stored values.
        note (str | None): Why examples are omitted, when they are.
    """

    name: str = Field(description="The field name (key used in filters / search_in).")
    type: FieldType = Field(description="The declared data type.")
    description: str | None = Field(default=None, description="What the field means.")
    scope: FieldScope = Field(description="One value per document, or one per chunk.")
    origin: FieldOrigin = Field(description="Who fills the field.")
    filterable: bool = Field(description="Usable as a filters key.")
    semantic: bool = Field(description="Searchable on its dense vector.")
    lexical: bool = Field(description="Searchable on its sparse vector.")
    required: bool = Field(description="Required at upload.")
    enum_values: list[str] | None = Field(default=None, description="Allowed values of an enum.")
    example_values: list[str] = Field(
        default_factory=list, description="Up to 10 stored values, most frequent first."
    )
    distinct_count: int = Field(description="Number of distinct stored values.")
    note: str | None = Field(default=None, description="Why examples are omitted, when they are.")


class SearchTargetGuide(BaseModel):
    """
    One valid ``search_in`` entry of the collection.

    Attributes:
        field (str): ``"content"`` (the chunk body) or a metadata field name.
        semantic (bool): The field has a dense vector to query.
        lexical (bool): The field has a sparse vector to query.
    """

    field: str = Field(description="'content' or a metadata field name.")
    semantic: bool = Field(description="The field has a dense vector to query.")
    lexical: bool = Field(description="The field has a sparse vector to query.")


class CollectionDescription(BaseModel):
    """
    The lean agent guide to one collection — what is in it and how to query it.

    Attributes:
        collection_id (str): The collection id.
        name (str): The collection name.
        document_count (int): Number of documents in the collection.
        title_field (str | None): The document-scope field used as each hit's display title.
        page_numbering (str): How hits locate pages (which field to cite).
        fields (list[FieldGuide]): Every metadata field of the schema.
        searchable_targets (list[SearchTargetGuide]): The valid ``search_in`` entries.
        filter_grammar (list[str]): The filter value forms the search route accepts.
        example_requests (list[dict[str, Any]]): Ready-to-send search request bodies.
    """

    collection_id: str = Field(description="The collection id.")
    name: str = Field(description="The collection name.")
    document_count: int = Field(description="Number of documents in the collection.")
    title_field: str | None = Field(default=None, description="Display-title field, if any.")
    page_numbering: str = Field(description="How hits locate pages (which field to cite).")
    fields: list[FieldGuide] = Field(description="Every metadata field of the schema.")
    searchable_targets: list[SearchTargetGuide] = Field(description="Valid search_in entries.")
    filter_grammar: list[str] = Field(description="The accepted filter value forms.")
    example_requests: list[dict[str, Any]] = Field(
        description="Ready-to-send search request bodies for this collection."
    )
