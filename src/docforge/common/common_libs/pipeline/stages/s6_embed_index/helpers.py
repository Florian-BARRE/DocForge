# ====== Code Summary ======
# S6IndexHelpers — pure-mapping static helper class for the S6 embedding and indexing stage.
# Builds Qdrant point payloads (lean filterable fields + base provenance) from chunk data.
# No logger binding: all methods are pure-mapping @staticmethod with no logging callsites.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.metadata import MetadataHelpers as _MetadataHelpers
from common_libs.search.field_index import FieldIndexHelpers

# Backward-compat alias for the private _field_attr function now in MetadataHelpers.
_field_attr = _MetadataHelpers.field_attr


class S6IndexHelpers:
    """
    Pure-mapping static helpers for the S6 embedding and indexing stage.

    Responsible for assembling Qdrant point payloads from chunk provenance data
    and filterable metadata field values (spec §7.1). All methods are stateless
    — no logging, no I/O.

    Note: no logger is bound because every method is a pure @staticmethod (no
    cls.logger callsites). Per project rules, logger binding is only added when
    at least one @classmethod uses it.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a static-only helper class."""
        raise TypeError("S6IndexHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_payload(
        chunk: Chunk,
        metadata_fields: list[Any],
        doc_meta: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the lean Qdrant payload: base provenance + filterable field values (spec §7.1).

        Only filterable fields are promoted to the payload — the rich content stays in
        Postgres. Hierarchical chunks carry a ``parent_id`` key so retrieval can roll a
        child up to its parent section.

        Args:
            chunk (Chunk): The chunk being indexed.
            metadata_fields (list[Any]): Collection metadata field definitions (3-flags + weights).
            doc_meta (dict[str, Any]): Document-level field values (implicit + user meta).

        Returns:
            dict[str, Any]: Qdrant payload dict for this chunk.
        """
        # 1. Build base provenance fields — always present on every Qdrant point.
        payload: dict[str, Any] = {
            "document_id": chunk.document_id,
            "config_hash": chunk.config_hash,
            "strategy": chunk.strategy,
            "token_count": chunk.token_count,
            "pages": chunk.prov.get("pages", []),
        }

        # 2. Hierarchical mode: carry the parent id so retrieval can roll a child up to its section.
        if chunk.parent_id:
            payload["parent_id"] = chunk.parent_id

        # 3. Promote filterable metadata field values into the payload.
        for f in metadata_fields:
            if _field_attr(f, "filterable", False):
                name = _field_attr(f, "field_name")
                value = FieldIndexHelpers.resolve_field_text(name, chunk, doc_meta)
                if value is not None:
                    payload[name] = value

        return payload
