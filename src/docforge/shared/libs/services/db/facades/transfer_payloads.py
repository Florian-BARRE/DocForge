# ====== Code Summary ======
# The transfer object the collection-EXPORT path crosses the façade boundary with.
# ``DocumentExportRows`` bundles EVERY per-document row a bundle must carry, read in one short
# session so the exporter streams a document at a time (never the whole collection in memory). Its
# metadata lists carry the field NAME (not the autoincrement field id) so the bundle stays portable
# across servers where the integer key is re-assigned. (Import restores table-by-table in FK order,
# so it needs no per-document payload — see CollectionTransferFacade.restore_rows.)

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin
from shared_libs.services.db.postgresql.tables import (
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Chunk,
    ChunkBlock,
    Document,
    Page,
)


@dataclass(slots=True)
class DocumentExportRows:
    """Every row a single document contributes to a bundle (read in one session)."""

    document: Document
    # (field_name, value, origin) — the name travels, not the server-local field id.
    metadata: list[tuple[str, Any, FieldOrigin]] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    tables: list[BlockTable] = field(default_factory=list)
    figures: list[BlockFigure] = field(default_factory=list)
    enrichments: list[BlockEnrichment] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    composition: list[ChunkBlock] = field(default_factory=list)
    # (chunk_id, field_name, value, origin) — same portability rule as document metadata.
    chunk_metadata: list[tuple[uuid.UUID, str, Any, FieldOrigin]] = field(default_factory=list)


__all__ = ["DocumentExportRows"]
