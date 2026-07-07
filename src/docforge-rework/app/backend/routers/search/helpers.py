# ====== Code Summary ======
# SearchHelpers — the pure, store-free mapping the search route leans on: locate the embed node in a
# collection's serialised pipeline blob (walking groups and foreach bodies), translate a simple
# {field: value} filter map into typed Qdrant Conditions over the FILTERABLE fields (reporting the
# fields that are not filterable so the route can 422), and flatten a hydrated SearchHit into its
# client model. Kept out of router.py so the route stays pure orchestration.

# ====== Standard Library Imports ======
from collections.abc import Iterator, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.services.db.facades import SearchHit
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import Condition, Match, MatchAny

# ====== Local Project Imports ======
from .models import SearchHitModel

# The registry family every embedder self-registers under (never string-literalled elsewhere).
EMBED_FAMILY = "embed"


class SearchHelpers:
    """Static, store-free helpers for the search route (blob lookup, filters, hit mapping)."""

    logger = loggerplusplus.bind(identifier="SearchHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def __iter_action_blobs(cls, blob: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield every action-node dict in a (possibly nested) group/foreach blob."""
        # 1. A foreach wraps a single group body — descend into it.
        if "body" in blob:
            yield from cls.__iter_action_blobs(blob["body"])
        # 2. A group holds children — descend into each.
        elif "nodes" in blob:
            for child in blob["nodes"]:
                yield from cls.__iter_action_blobs(child)
        # 3. A leaf action carries a family — it is what we iterate over.
        elif blob.get("family"):
            yield blob

    @classmethod
    def embed_node_blob(cls, pipeline: dict[str, Any]) -> ActionNodeBlob | None:
        """
        Find the collection's embed node in its serialised pipeline blob.

        Args:
            pipeline (dict): The stored pipeline blob (a serialised group topology).

        Returns:
            ActionNodeBlob | None: The embed action node, or None when the pipeline has none.
        """
        # 1. Scan every action node; the embed family is single-use, so the first is THE one.
        for node in cls.__iter_action_blobs(pipeline):
            if node.get("family") == EMBED_FAMILY:
                return ActionNodeBlob(**node)
        return None

    @staticmethod
    def build_conditions(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> tuple[list[Condition], list[str]]:
        """
        Translate a {field: value} filter map into typed Conditions over the FILTERABLE fields.

        Args:
            filters (dict | None): The requested constraints (field → scalar or list).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            tuple[list[Condition], list[str]]: The ANDed conditions, and the names of any
            requested fields that are unknown or not filterable (the route rejects these 422).
        """
        # 1. Only the fields flagged filterable are indexed for payload filtering in Qdrant.
        filterable = {row.field_name for row in schema if row.filterable}
        conditions: list[Condition] = []
        invalid: list[str] = []
        # 2. A list value → set membership (any-of); a scalar → exact match.
        for name, value in (filters or {}).items():
            if name not in filterable:
                invalid.append(name)
                continue
            if isinstance(value, list):
                conditions.append(MatchAny(field=name, values=value))
            else:
                conditions.append(Match(field=name, value=value))
        return conditions, invalid

    @staticmethod
    def to_hit(hit: SearchHit) -> SearchHitModel:
        """Flatten a hydrated SearchHit (chunk row + fused score) into its client model."""
        chunk = hit.chunk
        return SearchHitModel(
            chunk_id=str(chunk.id),
            document_id=str(chunk.document_id),
            score=hit.score,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            token_count=chunk.token_count,
        )


__all__ = ["SearchHelpers", "EMBED_FAMILY"]
