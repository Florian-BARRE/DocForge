# ====== Code Summary ======
# SYSTEM_METADATA_FIELDS: the catalog of implicit fields the pipeline extracts (spec §7.3).
# Every entry resolves to a real value at index time (see libs/retrieval/field_index
# and the engine's doc_meta). These fields are always present in every collection.

# ====== Standard Library Imports ======
from typing import Any

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
