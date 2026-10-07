# ====== Code Summary ======
# HitProjection — the per-request field selection of a search hit (the request's ``return_fields``).
# It validates the requested names against the hit's field names (+ ``metadata.<field>`` to keep a
# single metadata entry), projects a fully-built hit dict down to the requested keys (the identity
# keys chunk_id + document_id are always kept), and tells the read port which hydration reads it can
# SKIP (geometry, document metadata, document identity) — so a lean request is cheaper, not just
# smaller. ``without`` narrows a projection (or the full hit) so a caller lacking read_technical never
# receives the drawing geometry (TECHNICAL_GEOMETRY_FIELDS — page_number, the citation, stays). Model-agnostic: it works on plain dicts and is handed the allowed names by the caller.

# ====== Standard Library Imports ======
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any

# Always present in a projected hit — a hit without its identity cannot be cited or fetched.
IDENTITY_FIELDS: frozenset[str] = frozenset({"chunk_id", "document_id"})

# Hit fields derived from the chunk's source-block locations (one extra bulk read at hydration).
GEOMETRY_FIELDS: frozenset[str] = frozenset(
    {"block_ids", "page", "page_number", "bbox", "block_locations"}
)

# The geometry reserved to read_technical: the IR block ids and the drawing coordinates. The 1-based
# page_number stays — it is the reader-facing page to cite, part of the text surface.
TECHNICAL_GEOMETRY_FIELDS: frozenset[str] = GEOMETRY_FIELDS - {"page_number"}
# Hit fields derived from the owning document rows (+ the configured display-title field read).
DOCUMENT_FIELDS: frozenset[str] = frozenset({"filename", "document_title"})

# The hit field whose entries ``metadata.<field>`` selects one by one.
METADATA_FIELD = "metadata"
_METADATA_PREFIX = f"{METADATA_FIELD}."


@dataclass(frozen=True, slots=True)
class HitProjection:
    """
    The hit fields one search request asked for (``return_fields``).

    Attributes:
        fields (frozenset[str]): The top-level hit fields to keep (identity keys always included).
        metadata_keys (frozenset[str] | None): When only ``metadata.<field>`` entries were asked
            for, the metadata keys to keep; None when the whole metadata dict is kept or not
            requested at all (``fields`` decides which).
    """

    fields: frozenset[str]
    metadata_keys: frozenset[str] | None = None

    @classmethod
    def from_request(
        cls, return_fields: Iterable[str] | None, allowed: Collection[str]
    ) -> tuple["HitProjection | None", list[str]]:
        """
        Parse a request's ``return_fields`` into a projection, collecting the unknown names.

        Args:
            return_fields (Iterable[str] | None): The requested names; None = the full hit.
            allowed (Collection[str]): The projectable top-level hit field names.

        Returns:
            tuple[HitProjection | None, list[str]]: The projection (None = no projection, the full
            hit) and the sorted unknown names (non-empty → the request must be rejected).
        """
        # 1. No selection → the full hit, unchanged (the REST-compatible default).
        if return_fields is None:
            return None, []

        # 2. Split top-level names from metadata.<field> entries, collecting what is unknown.
        fields: set[str] = set(IDENTITY_FIELDS)
        metadata_keys: set[str] = set()
        unknown: set[str] = set()
        for name in return_fields:
            if name.startswith(_METADATA_PREFIX) and name[len(_METADATA_PREFIX) :]:
                metadata_keys.add(name[len(_METADATA_PREFIX) :])
            elif name in allowed:
                fields.add(name)
            else:
                unknown.add(name)

        # 3. A whole-metadata request wins over single keys; single keys alone keep a sub-dict.
        if metadata_keys and METADATA_FIELD not in fields:
            fields.add(METADATA_FIELD)
            return cls(frozenset(fields), frozenset(metadata_keys)), sorted(unknown)
        return cls(frozenset(fields)), sorted(unknown)

    @classmethod
    def without(
        cls, projection: "HitProjection | None", allowed: Collection[str], dropped: frozenset[str]
    ) -> "HitProjection":
        """
        Narrow a projection (None = the full hit) so it never returns the ``dropped`` fields.

        Args:
            projection (HitProjection | None): The request's projection; None = every allowed field.
            allowed (Collection[str]): The projectable top-level hit field names.
            dropped (frozenset[str]): The fields to withhold (identity keys are never dropped).

        Returns:
            HitProjection: The narrowed projection (metadata selection preserved).
        """
        # 1. The full hit becomes an explicit selection of every allowed field, minus the dropped.
        if projection is None:
            return cls(frozenset(allowed) - dropped | IDENTITY_FIELDS)
        return cls(projection.fields - (dropped - IDENTITY_FIELDS), projection.metadata_keys)

    @property
    def needs_geometry(self) -> bool:
        """Whether any block-location-derived field (page, bbox, block ids…) was requested."""
        return not self.fields.isdisjoint(GEOMETRY_FIELDS)

    @property
    def needs_document_metadata(self) -> bool:
        """Whether the document's filterable metadata (whole or per key) was requested."""
        return METADATA_FIELD in self.fields

    @property
    def needs_document_identity(self) -> bool:
        """Whether the document filename or display title was requested."""
        return not self.fields.isdisjoint(DOCUMENT_FIELDS)

    def apply(self, hit: dict[str, Any]) -> dict[str, Any]:
        """
        Project a fully-built hit dict down to the requested keys.

        Args:
            hit (dict[str, Any]): The full hit (every hit field present).

        Returns:
            dict[str, Any]: Only the requested keys; ``metadata`` restricted to the requested
            metadata keys the document actually carries when single keys were asked for.
        """
        # 1. Keep the requested top-level keys only (absent keys stay absent, never null).
        projected = {key: value for key, value in hit.items() if key in self.fields}

        # 2. Narrow metadata to the requested entries when single keys were asked for.
        if self.metadata_keys is not None and METADATA_FIELD in projected:
            metadata = projected[METADATA_FIELD] or {}
            projected[METADATA_FIELD] = {
                key: value for key, value in metadata.items() if key in self.metadata_keys
            }
        return projected


__all__ = [
    "HitProjection",
    "IDENTITY_FIELDS",
    "GEOMETRY_FIELDS",
    "TECHNICAL_GEOMETRY_FIELDS",
    "DOCUMENT_FIELDS",
    "METADATA_FIELD",
]
