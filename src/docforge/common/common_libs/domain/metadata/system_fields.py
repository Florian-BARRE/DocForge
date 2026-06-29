# ====== Code Summary ======
# SYSTEM_METADATA_FIELDS: the catalog of implicit fields the pipeline extracts (spec §7.3).
# Every entry resolves to a real value at index time (see libs/retrieval/field_index
# and the engine's doc_meta). These fields are always present in every collection.

# ====== Standard Library Imports ======
from typing import Any

# Implicit fields the pipeline ACTUALLY extracts (spec §7.3) — every entry resolves to a real
# value at index time (see libs/retrieval/field_index + the engine's doc_meta).
# Every entry is forced to origin="system" (alongside is_system=True) so system fields are never
# mistaken for user- or LLM-generated fields once the origin discriminator (migration 017) is in use.
SYSTEM_METADATA_FIELDS: list[dict[str, Any]] = [
    # ── File-intrinsic (S0) ──
    {"field_name": "filename", "field_type": "string", "filterable": True, "lexical": True, "is_system": True, "origin": "system"},
    {"field_name": "extension", "field_type": "string", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "file_size", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "has_scanned_pages", "field_type": "bool", "filterable": True, "is_system": True, "origin": "system"},
    # ── Document-derived ──
    {"field_name": "language", "field_type": "string", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "page_count", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "n_blocks", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "n_figures", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "n_tables", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
    # ── Chunk-level (provenance) ──
    {"field_name": "page", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "heading_path", "field_type": "string", "filterable": True, "semantic": True, "is_system": True, "origin": "system"},
    {"field_name": "block_type", "field_type": "string", "filterable": True, "is_system": True, "origin": "system"},
    {"field_name": "token_count", "field_type": "number", "filterable": True, "is_system": True, "origin": "system"},
]
