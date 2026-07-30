# ====== Code Summary ======
# The collection-contract vocabulary in ONE module: the schema enums (field type/origin/scope,
# unknown-field policy — shared with the storage layer) and the artefacts built on them.
# CollectionContract — the collection's contract as a pipeline RUN INPUT (bound via FromRunInput):
# accepted formats, size cap, the unknown-field policy, and the FULL metadata schema (every field
# with its type, required flag, three searchability axes, origin and scope — including the
# chunk-generated fields declared up front). The worker loads it from the collection row and hands
# it to the run; admit validates against it, metagen reads its generated targets, embed/index reads
# its searchable fields. The pipeline itself never touches the database.

# ====== Standard Library Imports ======
import uuid
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .base import Artifact


class FieldType(StrEnum):
    """Data type of a metadata field."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOL = "bool"
    KEYWORD_LIST = "keyword_list"  # a list of enumerable string tags
    DATETIME = "datetime"
    ENUM = "enum"  # a string constrained to the field's enum_values
    TEXT = "text"  # long free text (full-text Qdrant index when filterable)
    INTEGER_LIST = "integer_list"  # a list of integers (Qdrant matches any element)
    FLOAT_LIST = "float_list"  # a list of numbers (Qdrant matches any element)
    TEXT_LIST = "text_list"  # a list of free sentences (key findings, quotes…)


class FieldOrigin(StrEnum):
    """Where a metadata field's value comes from — drives who is allowed to fill it."""

    SYSTEM = "system"  # extracted by the pipeline (filename, language, page_count…)
    USER = "user"  # supplied by the caller at upload
    GENERATED = "generated"  # produced by the metagen (LLM) stage


class FieldScope(StrEnum):
    """At which granularity a field's VALUE lives — one per document, or one per chunk."""

    DOCUMENT = "document"  # one value per document (user upload, doc-level generation)
    CHUNK = "chunk"  # one value per chunk (post-chunk LLM generation) — origin must be generated


class UnknownFieldPolicy(StrEnum):
    """How a collection treats an uploaded metadata field absent from its schema."""

    REJECT = "reject"
    IGNORE = "ignore"


class MetadataFieldSpec(BaseModel):
    """One field of the metadata schema, as the pipeline sees it."""

    field_name: str
    field_type: FieldType
    required: bool = False
    filterable: bool = False
    lexical: bool = False
    semantic: bool = False
    origin: FieldOrigin = FieldOrigin.USER
    scope: FieldScope = FieldScope.DOCUMENT
    enum_values: list[str] | None = None


class CollectionContract(Artifact):
    """The collection contract the run is validated and driven by.

    Note: the unknown-field POLICY is not part of the contract — it is a behaviour knob of the
    admit node (pipeline config), mirroring where it is configured in the collection's pipeline.
    """

    collection_id: uuid.UUID
    name: str
    supported_formats: list[str] = Field(description="Accepted formats (file extensions).")
    max_file_size_bytes: int
    fields: list[MetadataFieldSpec] = Field(default_factory=list)


__all__ = [
    "FieldType",
    "FieldOrigin",
    "FieldScope",
    "UnknownFieldPolicy",
    "MetadataFieldSpec",
    "CollectionContract",
]
