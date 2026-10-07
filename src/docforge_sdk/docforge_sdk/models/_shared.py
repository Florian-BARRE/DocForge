# ====== Code Summary ======
# Vocabulary shared across resources, mirrored from the DocForge backend (never imported from it, to
# keep the SDK standalone). Holds the authorization enum + per-key permission scope, the metadata
# contract enums (FieldType/FieldOrigin/FieldScope), the document lifecycle enums (DocumentStatus/
# SourceKind) and the IR enrichment enums (EnrichmentKind/EnrichmentStatus).

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class Capability(StrEnum):
    """
    A coarse action class an endpoint requires of the calling key.

    ``READ`` is the legacy pre-split alias: the server normalizes it to ``READ_TEXT`` +
    ``READ_TECHNICAL`` and never returns it.
    """

    READ = "read"
    READ_TEXT = "read_text"
    READ_TECHNICAL = "read_technical"
    WRITE = "write"
    SEARCH = "search"
    CREATE = "create"
    ADMIN = "admin"


class KeyProfile(StrEnum):
    """A named capability preset offered at key creation."""

    AGENT_READER = "agent_reader"
    AGENT_SEARCHER = "agent_searcher"
    OPERATOR = "operator"
    ADMIN = "admin"


class FieldType(StrEnum):
    """Data type of a metadata field — drives validation and storage."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOL = "bool"
    KEYWORD_LIST = "keyword_list"
    DATETIME = "datetime"
    ENUM = "enum"
    TEXT = "text"
    INTEGER_LIST = "integer_list"
    FLOAT_LIST = "float_list"
    TEXT_LIST = "text_list"


class FieldOrigin(StrEnum):
    """Where a metadata field's value comes from — drives who may fill it."""

    SYSTEM = "system"
    USER = "user"
    GENERATED = "generated"


class FieldScope(StrEnum):
    """At which granularity a field's value lives — one per document, or one per chunk."""

    DOCUMENT = "document"
    CHUNK = "chunk"


class SourceKind(StrEnum):
    """How a document's pages were acquired — routes parsing (text vs OCR/VLM)."""

    DIGITAL_BORN = "digital_born"
    SCANNED = "scanned"
    MIXED = "mixed"


class DocumentStatus(StrEnum):
    """A document's ingestion lifecycle state."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class EnrichmentKind(StrEnum):
    """What an IR block enrichment produced."""

    CLASSIFY = "classify"
    OCR = "ocr"
    VLM = "vlm"
    CHART_TO_DATA = "chart_to_data"
    TABLE_SUMMARY = "table_summary"


class EnrichmentStatus(StrEnum):
    """The outcome of a block enrichment run."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class KeyPermissions(BaseModel):
    """
    The per-key permission scope stored on an API key.

    A key with ``null`` permissions is full access (root) and is represented as ``None`` at the call
    site, never as an instance of this model — this model always describes a SCOPED key.

    Attributes:
        capabilities (list[Capability]): The action classes the key grants (an empty list = a key
            that can authenticate but is authorized for nothing).
        collections (list[str]): Either ``["*"]`` (every collection) or an explicit list of
            collection UUID strings the key is scoped to.
        profile (KeyProfile | None): A named preset — give it INSTEAD of ``capabilities`` and the
            server expands it to the preset's explicit list (stored for display).
    """

    capabilities: list[Capability] = Field(
        default_factory=list,
        description="The action classes this key grants (read_text / read_technical / write / "
        "search / create / admin; the legacy 'read' = read_text + read_technical). May be omitted "
        "when 'profile' is given.",
    )
    collections: list[str] = Field(
        description="Collection scope: ['*'] for all, else explicit collection UUID strings."
    )
    profile: KeyProfile | None = Field(
        default=None,
        description="Named capability preset (agent_reader / agent_searcher / operator / admin). "
        "Given instead of 'capabilities', it expands to the preset; stored for display only.",
    )


__all__ = [
    "Capability",
    "KeyProfile",
    "FieldType",
    "FieldOrigin",
    "FieldScope",
    "SourceKind",
    "DocumentStatus",
    "EnrichmentKind",
    "EnrichmentStatus",
    "KeyPermissions",
]
