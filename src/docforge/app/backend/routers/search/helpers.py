# ====== Code Summary ======
# SearchHelpers — the pure, store-free mapping the search route leans on: locate the embed node in a
# collection's serialised pipeline blob (via the shared EmbedBlobResolver), translate a simple
# {field: value} filter map into typed Qdrant Conditions over the FILTERABLE fields (reporting the
# fields that are not filterable so the route can 422), and flatten a graph Hit into its client
# model. Kept out of router.py so the route stays pure orchestration.

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.pipelines.reachability import ProbeStatus
from shared_libs.public_models.search import CONTENT_FIELD, Hit, SearchTarget
from shared_libs.services.db.facades import DatabaseHelpers
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import (
    Condition,
    PayloadType,
    build_match_conditions,
    parse_range,
)

# ====== Local Project Imports ======
from .models import BlockLocationModel, SearchHitModel, SearchTargetModel


class SearchHelpers:
    """Static, store-free helpers for the search route (blob lookup, filters, hit mapping)."""

    logger = loggerplusplus.bind(identifier="SearchHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def __iter_action_blobs(cls, blob: dict[str, Any]):  # type: ignore[no-untyped-def]
        """Yield every action-node dict in a (possibly nested) group/foreach search blob."""
        # 1. A foreach wraps a single group body; a group holds children — descend into both.
        if "body" in blob:
            yield from cls.__iter_action_blobs(blob["body"])
        elif "nodes" in blob:
            for child in blob["nodes"]:
                yield from cls.__iter_action_blobs(child)
        # 2. A leaf action carries a family — it is what we iterate over.
        elif blob.get("family"):
            yield blob

    @classmethod
    def score_kind(cls, search_blob: dict[str, Any] | None) -> str:
        """
        Classify what a collection's search score represents, so the client can label it.

        Cheap, store-free blob inspection (no I/O): a rerank node makes the delivered score a
        cross-encoder relevance score; otherwise it is the retrieve node's server-side fusion score
        (RRF by default, DBSF when configured). An empty/None blob is the stock default (RRF).

        Args:
            search_blob (dict | None): The collection's stored search blob ({}/None = stock default).

        Returns:
            str: One of 'cross_encoder_rerank', 'dbsf_fusion', 'rrf_fusion'.
        """
        # 1. Empty/None → the stock default topology (hybrid retrieve, RRF fusion, no rerank).
        blob = search_blob or {}
        if not blob.get("nodes") and "body" not in blob:
            return "rrf_fusion"
        # 2. A rerank node re-scores the pool — the delivered score is then the cross-encoder's.
        actions = list(cls.__iter_action_blobs(blob))
        if any(node.get("family") == "rerank" for node in actions):
            return "cross_encoder_rerank"
        # 3. Otherwise the retrieve node's fusion strategy decides (defaults to RRF).
        retrieve = next((node for node in actions if node.get("family") == "retrieve"), None)
        fusion = (retrieve or {}).get("config", {}).get("fusion", "rrf")
        return "dbsf_fusion" if fusion == "dbsf" else "rrf_fusion"

    @staticmethod
    def embed_node_blob(pipeline: dict[str, Any]) -> ActionNodeBlob | None:
        """
        Find the collection's embed node in its serialised pipeline blob.

        Args:
            pipeline (dict): The stored pipeline blob (a serialised group topology).

        Returns:
            ActionNodeBlob | None: The embed action node, or None when the pipeline has none.
        """
        # 1. Delegate the (possibly nested) walk to the shared resolver; the embed family is
        #    single-use, so it returns THE one. None when the pipeline carries no embedder.
        node = EmbedBlobResolver.find_embed_node(pipeline)
        return ActionNodeBlob(**node) if node is not None else None

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
        # 1. Only the fields flagged filterable are indexed for payload filtering in Qdrant;
        #    a non-filterable field is reported so the route can 422, never silently matched.
        filterable = {row.field_name for row in schema if row.filterable}
        accepted: dict[str, Any] = {}
        invalid: list[str] = []
        for name, value in (filters or {}).items():
            if name in filterable:
                accepted[name] = value
            else:
                invalid.append(name)
        # 2. Build the conditions over the accepted subset with the shared mapping (list → any-of,
        #    scalar → exact) — order preserved, so the built filter is byte-identical.
        return build_match_conditions(accepted), invalid

    @staticmethod
    def enum_violations(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> list[str]:
        """
        Report filter values that fall OUTSIDE a filterable field's declared enum.

        A field declared with ``enum_values`` accepts only those members (the same rule upload-time
        admission enforces). Filtering it with a value outside the set otherwise returns 200 with 0
        hits — a typo'd filter reads as "nothing matches" and can mask a real result set — so it is
        rejected 422 here, naming the field and its allowed values. Non-enum and non-filterable
        fields are not this check's concern (filterability is gated separately).

        Args:
            filters (dict | None): The requested constraints (field → scalar or list).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            list[str]: One human-readable message per out-of-enum value (empty when all valid).
        """
        # 1. Index the filterable enum fields → their allowed value set (skip fields without one).
        enums = {
            row.field_name: getattr(row, "enum_values", None)
            for row in schema
            if row.filterable and getattr(row, "enum_values", None)
        }
        # 2. Every requested value (a list filter is any-of) must be a declared member.
        errors: list[str] = []
        for name, value in (filters or {}).items():
            allowed = enums.get(name)
            if allowed is None:
                continue
            for item in value if isinstance(value, list) else [value]:
                if item not in allowed:
                    errors.append(f"field '{name}' value {item!r} is not one of {allowed}")
        return errors

    # Payload index types a range filter can constrain (an exact-match keyword/bool cannot).
    _RANGE_TYPED = frozenset({PayloadType.INTEGER, PayloadType.FLOAT, PayloadType.DATETIME})

    @staticmethod
    def _range_payload_type(field: MetadataField | None) -> PayloadType | None:
        """
        Resolve a field's Qdrant payload index type, defensively — None when unresolvable.

        Only a range filter needs a field's type, so this is looked up lazily (never for a plain
        scalar/list filter). A field object that carries no ``field_type`` (a lightweight stand-in
        shape) or an unmapped type yields None rather than raising — the caller treats None as
        "not range-typed" and reports a clean 422 instead of a 500.
        """
        # 1. A missing field (unknown/non-filterable) or a shape without a declared type → None.
        field_type = getattr(field, "field_type", None)
        if field_type is None:
            return None
        # 2. Map the declared type to its payload index type; an unmapped type is treated as None.
        try:
            return DatabaseHelpers.payload_type_for(field_type)
        except KeyError:
            return None

    @staticmethod
    def range_violations(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> list[str]:
        """
        Report range filters (``{gte/gt/lte/lt: bound}`` mappings) that a field cannot accept.

        A range is only valid on a range-typed FILTERABLE field (integer/float/datetime); on a
        keyword/bool field it would otherwise be silently mistranslated. The range's shape is also
        validated (allowed keys, coercible bounds, ordered bounds) and its bound kind must match
        the field's declared type — a datetime field needs ISO-8601 bounds, a numeric field numeric
        bounds. Non-filterable fields are the filterability gate's concern, not this check's.

        This runs on EVERY search, so it must never raise: a plain scalar/list filter is skipped
        untouched (its field type is never inspected), and only an actual range mapping triggers the
        (defensive) field-type lookup — an unknown/non-range-typed field yields a 422 message, not a
        crash.

        Args:
            filters (dict | None): The requested constraints (field → scalar, list, or range map).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            list[str]: One human-readable message per offending range (empty when all valid).
        """
        # 1. Index the FILTERABLE fields by name — resolved lazily, only when a range needs a type.
        by_name = {row.field_name: row for row in schema if getattr(row, "filterable", False)}
        errors: list[str] = []
        for name, value in (filters or {}).items():
            # 2. Only a mapping is a range; scalars/lists are validated by the other gates untouched.
            if not isinstance(value, Mapping):
                continue
            # 3. A range on an unknown/non-filterable field is the filterability gate's concern.
            if name not in by_name:
                continue
            # 4. Resolve the field's payload type defensively; only range-typed accepts a range.
            ptype = SearchHelpers._range_payload_type(by_name[name])
            if ptype not in SearchHelpers._RANGE_TYPED:
                label = ptype.value if ptype is not None else "non-range"
                errors.append(
                    f"field '{name}' is not range-typed ({label}) — a range filter needs an "
                    f"integer, float or datetime field"
                )
                continue
            # 5. Validate the range shape; a malformed range surfaces its reason as a 422 message.
            try:
                parsed = parse_range(name, value)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            # 6. The bound kind must match the declared type (datetime ↔ DATETIME, numeric ↔ number).
            if parsed.is_datetime != (ptype == PayloadType.DATETIME):
                expected = "ISO-8601 datetime" if ptype == PayloadType.DATETIME else "numeric"
                errors.append(f"field '{name}' expects {expected} range bounds")
        return errors

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
    def encode_failure_http(status: ProbeStatus, detail: str) -> HTTPException:
        """
        Map a classified query-embedder probe outcome onto an HONEST encode-failure HTTP error.

        The point is that a caller can tell "fix your config" from "retry shortly": a permanent
        config/auth fault is a 424 (Failed Dependency) naming WHAT is wrong, never a transient 503.

        Mapping:
            - ``unreachable``   → 424 ``embedder_unreachable`` (dead host / transport / drifted blob).
            - ``auth_failed``   → 424 ``embedder_auth_failed`` (the endpoint rejected the credentials).
            - anything else (``ok`` / ``not_configured`` / ``skipped``) → 503 ``embedder_overloaded``
              (the embedder answered the probe, so the original failure was genuinely transient).

        Args:
            status (ProbeStatus): The query-embedder probe outcome.
            detail (str): The human-readable reason (the original encode failure message).

        Returns:
            HTTPException: The status-coded, machine-readable error the route raises.
        """
        # 1. Permanent config faults are a Failed-Dependency 424 with a machine-readable code.
        if status == ProbeStatus.UNREACHABLE:
            return HTTPException(
                status_code=424,
                detail={"code": "embedder_unreachable", "detail": detail},
            )
        if status == ProbeStatus.AUTH_FAILED:
            return HTTPException(
                status_code=424,
                detail={"code": "embedder_auth_failed", "detail": detail},
            )
        # 2. The embedder answered the probe → the failure was transient; a retryable 503.
        return HTTPException(
            status_code=503,
            detail={"code": "embedder_overloaded", "detail": detail},
        )

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
        # 1. chunk_index/token_count + source identity/metadata + block location live in the
        #    hydrated metadata bag (never on the Hit's spine) — the read port fills them so the hit
        #    self-cites (which section, which document, and WHERE on the page).
        metadata = hit.metadata or {}
        return SearchHitModel(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            filename=metadata.get("filename"),
            document_title=metadata.get("document_title"),
            heading_path=metadata.get("heading_path") or [],
            metadata=metadata.get("document_metadata") or {},
            score=hit.score,
            text=hit.text or "",
            chunk_index=metadata.get("chunk_index", 0),
            token_count=metadata.get("token_count", 0),
            block_ids=metadata.get("block_ids") or [],
            page=metadata.get("page"),
            bbox=metadata.get("bbox"),
            block_locations=[
                BlockLocationModel(page=loc["page"], bbox=loc["bbox"])
                for loc in (metadata.get("block_locations") or [])
            ],
        )


__all__ = ["SearchHelpers"]
