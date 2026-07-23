# ====== Code Summary ======
# SearchHelpers — the pure, store-free mapping the search route leans on: locate the embed node in a
# collection's serialised pipeline blob (walking groups and foreach bodies), translate a simple
# {field: value} filter map into typed Qdrant Conditions over the FILTERABLE fields (reporting the
# fields that are not filterable so the route can 422), and flatten a graph Hit into its client
# model. Kept out of router.py so the route stays pure orchestration.

# ====== Standard Library Imports ======
from collections.abc import Iterator, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.public_models.search import CONTENT_FIELD, Hit, SearchTarget
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import Condition, Match, MatchAny

# ====== Local Project Imports ======
from .models import SearchHitModel, SearchTargetModel

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
    def validate_search_targets(
        search_in: list[SearchTargetModel] | None, schema: Sequence[MetadataField]
    ) -> list[str]:
        """
        Validate the requested search targets against the collection's indexed vectors.

        A target may name ``"content"`` (always both modalities) or a metadata field; a modality is
        only valid when that field was actually indexed for it (semantic → dense, lexical → bm25).
        A target asking for a vector that was never indexed, or a selection with no modality at all,
        is a caller error the route rejects 422 BEFORE any spend.

        Args:
            search_in (list[SearchTargetModel] | None): The requested targets (None = default path).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            list[str]: Human-readable error messages (empty when the selection is valid). None
            search_in yields no errors (the unchanged content default is always valid).
        """
        # 1. None → the default content path, always valid; nothing to check.
        if search_in is None:
            return []

        # 2. The three surfaces a target may legitimately name.
        known = {row.field_name for row in schema}
        semantic = {row.field_name for row in schema if row.semantic}
        lexical = {row.field_name for row in schema if row.lexical}

        # 3. Every target must resolve to at least one indexed vector; the whole set must select one.
        errors: list[str] = []
        any_modality = False
        for target in search_in:
            is_content = target.field == CONTENT_FIELD
            if not is_content and target.field not in known:
                errors.append(f"unknown field '{target.field}'")
                continue
            if not target.semantic and not target.lexical:
                errors.append(f"target '{target.field}' selects no modality (semantic or lexical)")
                continue
            if target.semantic:
                any_modality = True
                if not is_content and target.field not in semantic:
                    errors.append(f"field '{target.field}' has no semantic (dense) vector")
            if target.lexical:
                any_modality = True
                if not is_content and target.field not in lexical:
                    errors.append(f"field '{target.field}' has no lexical (bm25) vector")
        if not any_modality:
            errors.append("select at least one modality (semantic or lexical) to search")
        return errors

    @staticmethod
    def to_search_targets(
        search_in: list[SearchTargetModel] | None,
    ) -> list[SearchTarget] | None:
        """
        Map the request's search-target models to the public SearchTarget artefacts (or None).

        Args:
            search_in (list[SearchTargetModel] | None): The requested targets (None passed through).

        Returns:
            list[SearchTarget] | None: The public targets, or None to let the default apply.
        """
        # 1. None rides through so the service applies the content default (unchanged behaviour).
        if search_in is None:
            return None
        # 2. One public target per requested model (validated already by the route).
        return [
            SearchTarget(field=t.field, semantic=t.semantic, lexical=t.lexical) for t in search_in
        ]

    @staticmethod
    def to_hit_model(hit: Hit) -> SearchHitModel:
        """
        Flatten a graph Hit (the search pipeline's terminal unit) into its client model.

        The graph's Hit carries the ranking fields directly (chunk_id, document_id, score, text);
        chunk_index and token_count ride along in ``Hit.metadata`` (the read port hydrates them
        there), so they are lifted out here into the flat client shape.

        Args:
            hit (Hit): One hydrated, ranked hit produced by the search pipeline.

        Returns:
            SearchHitModel: The flat, client-facing view of the hit.
        """
        # 1. chunk_index/token_count live in the hydrated metadata bag (never on the Hit's spine).
        metadata = hit.metadata or {}
        return SearchHitModel(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            score=hit.score,
            text=hit.text or "",
            chunk_index=metadata["chunk_index"],
            token_count=metadata["token_count"],
        )


__all__ = ["SearchHelpers", "EMBED_FAMILY"]
