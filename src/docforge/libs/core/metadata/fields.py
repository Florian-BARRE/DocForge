# ====== Code Summary ======
# Metadata field models + the system/implicit field catalog (spec §3 MetaField, §7).
# Shared domain layer used by the collections, config, documents and playground routers —
# kept out of any single router so the API structure can evolve without moving the contract.

# ====== Standard Library Imports ======
from typing import Any, Iterable, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# Field types a metadata field can declare (spec §3 MetaField.type).
MetaFieldType = Literal["string", "number", "date", "bool", "enum", "string[]"]


class MetaFieldSpec(BaseModel):
    """
    A metadata field definition (spec §3 MetaField, §7.2 three orthogonal capabilities).

    Three independent search roles + RRF fusion weights:
    - filterable → indexed Qdrant payload (exact/range filter)
    - lexical    → dedicated BM25 sparse vector (keyword match)
    - semantic   → dedicated named dense vector (fuzzy/semantic match)
    """

    model_config = ConfigDict(from_attributes=True)

    field_name: str = Field(..., min_length=1, max_length=255)
    field_type: MetaFieldType = "string"
    required: bool = False
    filterable: bool = False
    lexical: bool = False
    semantic: bool = False
    enum_values: list[str] | None = None
    is_system: bool = False


class MetadataFieldsResponse(BaseModel):
    """System metadata field catalog (the always-present, auto-extracted fields)."""

    system_fields: list[MetaFieldSpec]


# Implicit fields the pipeline ACTUALLY extracts (spec §7.3) — every entry resolves to a real
# value at index time (see libs/retrieval/field_index + the engine's doc_meta).
SYSTEM_METADATA_FIELDS: list[dict[str, Any]] = [
    # ── File-intrinsic (S0) ──
    {"field_name": "filename", "field_type": "string", "filterable": True, "lexical": True, "is_system": True},
    {"field_name": "extension", "field_type": "string", "filterable": True, "is_system": True},
    {"field_name": "file_size", "field_type": "number", "filterable": True, "is_system": True},
    {"field_name": "has_scanned_pages", "field_type": "bool", "filterable": True, "is_system": True},
    # ── Document-derived ──
    {"field_name": "language", "field_type": "string", "filterable": True, "is_system": True},
    {"field_name": "page_count", "field_type": "number", "filterable": True, "is_system": True},
    {"field_name": "n_blocks", "field_type": "number", "filterable": True, "is_system": True},
    {"field_name": "n_figures", "field_type": "number", "filterable": True, "is_system": True},
    {"field_name": "n_tables", "field_type": "number", "filterable": True, "is_system": True},
    # ── Chunk-level (provenance) ──
    {"field_name": "page", "field_type": "number", "filterable": True, "is_system": True},
    {"field_name": "heading_path", "field_type": "string", "filterable": True, "semantic": True, "is_system": True},
    {"field_name": "block_type", "field_type": "string", "filterable": True, "is_system": True},
    {"field_name": "token_count", "field_type": "number", "filterable": True, "is_system": True},
]


def _field_attr(field: Any, name: str, default: Any = None) -> Any:
    """Read a metadata-field attribute from an ORM row, a Pydantic model, or a plain dict."""
    if isinstance(field, dict):
        return field.get(name, default)
    return getattr(field, name, default)


def schema_field_dicts(metadata_fields: Iterable[Any]) -> list[dict[str, Any]]:
    """
    Normalize a collection's metadata fields into the canonical plain-dict schema.

    Single source of truth shared by the retrieval engine (which reads ``field_name`` +
    ``semantic``/``lexical``/``filterable``) and the discovery endpoint (which also needs
    ``field_type``/``enum_values``/``required``/``is_system`` to derive filter/weight choices),
    so the two can never disagree on what a collection's fields are.

    Args:
        metadata_fields (Iterable): ORM rows, MetaFieldSpec models, or dicts.

    Returns:
        list[dict[str, Any]]: One dict per field with the full canonical key set.
    """
    return [
        {
            "field_name": _field_attr(f, "field_name"),
            "field_type": _field_attr(f, "field_type", "string"),
            "required": bool(_field_attr(f, "required", False)),
            "filterable": bool(_field_attr(f, "filterable", False)),
            "semantic": bool(_field_attr(f, "semantic", False)),
            "lexical": bool(_field_attr(f, "lexical", False)),
            "enum_values": _field_attr(f, "enum_values"),
            "is_system": bool(_field_attr(f, "is_system", False)),
        }
        for f in metadata_fields
    ]
