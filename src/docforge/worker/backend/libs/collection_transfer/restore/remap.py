# ====== Code Summary ======
# RemapContext + RemapBuilder — the id-remap plan for an import. An import ALWAYS creates a NEW
# collection, and every globally-unique id (document/chunk/page/enrichment/attempt/entity UUID and
# the string block id) is REGENERATED so a bundle can be restored anywhere — including back onto the
# server it came from (id preservation would collide on the global primary keys, and nothing external
# references these ids). The builder streams the id-defining bundle files once to mint fresh ids and
# record old→new, so the restore pass can rewrite every foreign key consistently. The block id keeps
# its "<document_id>:<suffix>" shape, re-namespaced onto the NEW document id. Blob hashes are
# content-addressed (sha256), NOT ids — they are never remapped.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

# ====== Local Project Imports ======
from ..bundle import BundleReader
from ..paths import BundlePaths


@dataclass(slots=True)
class RemapContext:
    """The old→new id maps applied to every restored row (plus the field name→new id map)."""

    field_ids: dict[str, int]
    documents: dict[str, uuid.UUID] = field(default_factory=dict)
    pages: dict[str, uuid.UUID] = field(default_factory=dict)
    blocks: dict[str, str] = field(default_factory=dict)
    enrichments: dict[str, uuid.UUID] = field(default_factory=dict)
    attempts: dict[str, uuid.UUID] = field(default_factory=dict)
    chunks: dict[str, uuid.UUID] = field(default_factory=dict)
    entities: dict[str, uuid.UUID] = field(default_factory=dict)

    def remap_block_id(self, old_block_id: str, old_document_id: str) -> str:
        """Re-namespace a block id onto the NEW document id, preserving its suffix."""
        new_document_id = self.documents[old_document_id]
        prefix = f"{old_document_id}:"
        suffix = old_block_id[len(prefix) :] if old_block_id.startswith(prefix) else old_block_id
        return f"{new_document_id}:{suffix}"


class RemapBuilder:
    """Builds a RemapContext by streaming the bundle's id-defining files once each."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RemapBuilder is a static-only class and cannot be instantiated.")

    @staticmethod
    def build(reader: BundleReader, field_ids: dict[str, int]) -> RemapContext:
        """
        Mint fresh ids for every entity and record the old→new mapping.

        Documents are mapped first because the block id remap re-namespaces onto the new document id.

        Args:
            reader (BundleReader): The validated bundle reader.
            field_ids (dict[str, int]): field_name → the freshly-minted metadata field id.

        Returns:
            RemapContext: The complete id-remap plan for the restore pass.
        """
        ctx = RemapContext(field_ids=field_ids)
        for row in reader.iter_rows(BundlePaths.DOCUMENTS):
            ctx.documents[row["id"]] = uuid.uuid4()
        for row in reader.iter_rows(BundlePaths.PAGES):
            ctx.pages[row["id"]] = uuid.uuid4()
        for row in reader.iter_rows(BundlePaths.IR_BLOCKS):
            ctx.blocks[row["id"]] = ctx.remap_block_id(row["id"], row["document_id"])
        for row in reader.iter_rows(BundlePaths.IR_ENRICHMENTS):
            ctx.enrichments[row["id"]] = uuid.uuid4()
        for row in reader.iter_rows(BundlePaths.IR_ENRICHMENT_ATTEMPTS):
            ctx.attempts[row["id"]] = uuid.uuid4()
        for row in reader.iter_rows(BundlePaths.CHUNKS):
            ctx.chunks[row["id"]] = uuid.uuid4()
        for row in reader.iter_rows(BundlePaths.ENTITY_MENTIONS):
            ctx.entities[row["id"]] = uuid.uuid4()
        return ctx


__all__ = ["RemapContext", "RemapBuilder"]
