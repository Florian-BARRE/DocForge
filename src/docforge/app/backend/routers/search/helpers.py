# ====== Code Summary ======
# SearchHelpers — the pure, store-free mapping the search route leans on: locate the embed node in a
# collection's serialised pipeline blob (via the shared EmbedBlobResolver), translate a simple
# {field: value} filter map into typed Qdrant Conditions over the FILTERABLE fields (reporting the
# fields that are not filterable so the route can 422), gate operator objects ({field: {"<op>": v}})
# against each field's type via the shared FilterOperatorGrammar, map enum filter values (bare or
# eq/in/not/not_in operands) onto their declared members ignoring case, resolve the collection's
# display-title field, and flatten a graph Hit / a filter hint into its client model. Kept out of
# router.py so the route stays pure orchestration.

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
from shared_libs.pipelines.search.nodes.rerank.cross_encoder.core import _RERANK_DEGRADED
from shared_libs.public_models import FieldScope
from shared_libs.public_models.search import CONTENT_FIELD, Hit, SearchTarget
from shared_libs.services.db.facades import DatabaseHelpers
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import (
    MAX_LIST_VALUES,
    PATTERN_OPS,
    Condition,
    FilterOp,
    FilterOperatorGrammar,
    PayloadType,
    build_match_conditions,
)

# ====== Local Project Imports ======
from ...libs.search import FilterHint
from .models import BlockLocationModel, SearchHint, SearchHitModel, SearchTargetModel


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

    @staticmethod
    def __enum_members(name: str, value: Any, allowed: list[Any], errors: list[str]) -> Any:
        """
        Map an enum filter operand (scalar or list) onto its declared members, ignoring case.

        Args:
            name (str): The enum field.
            value (Any): The operand (a scalar, or a list for any-of / not_in).
            allowed (list): The field's declared members.
            errors (list[str]): Collects one message per value outside the enum (mutated).

        Returns:
            Any: The operand with each item replaced by its member (unknown items kept as sent).
        """
        # 1. Exact member first, then a case-insensitive match; an unknown item is reported.
        by_lower = {str(member).lower(): member for member in allowed}
        items = value if isinstance(value, list) else [value]
        canonical: list[Any] = []
        for item in items:
            member = item if item in allowed else by_lower.get(str(item).lower())
            if member is None:
                errors.append(
                    f"field '{name}' value {item!r} is not an allowed value — allowed values: "
                    f"{', '.join(str(member) for member in allowed)}"
                )
            canonical.append(member if member is not None else item)
        return canonical if isinstance(value, list) else canonical[0]

    @classmethod
    def score_kind(cls, search_blob: dict[str, Any] | None, rerank_degraded: bool = False) -> str:
        """
        Classify what a collection's search score represents, so the client can label it.

        Cheap, store-free blob inspection (no I/O): a rerank node makes the delivered score a
        cross-encoder relevance score; otherwise it is the retrieve node's server-side fusion score
        (RRF by default, DBSF when configured). An empty/None blob is the stock default (RRF).

        The label reflects the ACTUAL score source, not merely the topology: when the rerank stage
        DEGRADED at run time (a slow/cold reranker, so it handed back the fusion-order pool), the
        delivered score is the fusion score — ``rerank_degraded=True`` steps the label back to the
        fusion kind instead of mislabelling a fusion score as a cross-encoder score.

        Args:
            search_blob (dict | None): The collection's stored search blob ({}/None = stock default).
            rerank_degraded (bool): Whether this run's rerank degraded to fusion-order (from the
                run's ``SearchResult.debug`` — see ``rerank_degraded``). Ignored for a blob with no
                rerank node.

        Returns:
            str: One of 'cross_encoder_rerank', 'dbsf_fusion', 'rrf_fusion'.
        """
        # 1. Empty/None → the stock default topology (hybrid retrieve, RRF fusion, no rerank).
        blob = search_blob or {}
        if not blob.get("nodes") and "body" not in blob:
            return "rrf_fusion"
        # 2. A rerank node re-scores the pool → the delivered score is the cross-encoder's — UNLESS
        #    it degraded to fusion-order at run time, in which case the score is the fusion score.
        actions = list(cls.__iter_action_blobs(blob))
        if not rerank_degraded and any(node.get("family") == "rerank" for node in actions):
            return "cross_encoder_rerank"
        # 3. Otherwise the retrieve node's fusion strategy decides (defaults to RRF).
        retrieve = next((node for node in actions if node.get("family") == "retrieve"), None)
        fusion = (retrieve or {}).get("config", {}).get("fusion", "rrf")
        return "dbsf_fusion" if fusion == "dbsf" else "rrf_fusion"

    @classmethod
    def rerank_degraded(cls, debug: dict[str, Any] | None) -> bool:
        """
        Whether the run's rerank stage degraded to fusion-order (its score is a fusion score).

        The rerank node stamps a specific note into ``SearchResult.debug['degraded']`` when it
        gives up on a slow/cold reranker and returns the incoming fusion-order pool. Detecting THAT
        note — distinct from an encode-axis degradation, after which the rerank still truly ran on
        the fused pool — is what lets ``score_kind`` label the delivered score honestly.

        Args:
            debug (dict | None): The run's ``SearchResult.debug`` bag ({}/None = healthy run).

        Returns:
            bool: True when the rerank degrade note is present in the run's degrade trace.
        """
        # 1. The degrade bag joins one or more notes; the rerank marker rides in as a substring.
        note = (debug or {}).get("degraded") or ""
        return _RERANK_DEGRADED in note

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

    # Max values one list filter may carry (any-of): a larger list is a caller error, never a fan-out.
    MAX_FILTER_LIST_VALUES = MAX_LIST_VALUES

    @staticmethod
    def list_violations(filters: dict[str, Any] | None) -> list[str]:
        """
        Report list filters that are empty or longer than ``MAX_FILTER_LIST_VALUES``.

        An empty any-of list would reach Qdrant as an empty ``should`` — which Qdrant treats as "no
        constraint", silently WIDENING the search instead of matching nothing. An oversized list
        would fan out one stored-value lookup per item. Both are rejected 422 for every field type.

        Args:
            filters (dict | None): The requested constraints (field → scalar, list, or range map).

        Returns:
            list[str]: One human-readable message per offending filter (empty when all valid).
        """
        # 1. Only list values are checked; scalars and range mappings are other gates' concern.
        errors: list[str] = []
        for name, value in (filters or {}).items():
            if not isinstance(value, list):
                continue
            if not value:
                errors.append(
                    f"filter '{name}': an empty list matches nothing — omit the filter or give at "
                    f"least one value"
                )
            elif len(value) > SearchHelpers.MAX_FILTER_LIST_VALUES:
                errors.append(
                    f"filter '{name}': {len(value)} values exceed the maximum of "
                    f"{SearchHelpers.MAX_FILTER_LIST_VALUES} per field"
                )
        return errors

    @staticmethod
    def canonical_enum_filters(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """
        Map ENUM filter values onto their declared members, ignoring case; report unknown values.

        A field declared with ``enum_values`` accepts only those members (the same rule upload-time
        admission enforces). A value differing from a member only by case is rewritten to that
        member (``"POLICY"`` → ``"policy"``); a value matching no member otherwise returns 200 with 0
        hits — a typo'd filter reads as "nothing matches" — so it is reported for a 422 naming the
        field and its allowed values. Non-enum and non-filterable fields pass through untouched
        (filterability is gated separately).

        Args:
            filters (dict | None): The requested constraints (field → scalar or list).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            tuple[dict | None, list[str]]: The filter map with enum values canonicalized (None when
            the request had none), and one message per value outside its enum (empty when valid).
        """
        # 1. Index the filterable enum fields → their allowed members (skip fields without one).
        enums = {
            row.field_name: list(getattr(row, "enum_values", None) or [])
            for row in schema
            if row.filterable and getattr(row, "enum_values", None)
        }
        if filters is None:
            return None, []

        # 2. Rewrite every enum value (a list filter is any-of) to its member, or report it. An
        #    operator object maps its eq/in/not/not_in operand the same way; contains/prefix/exists
        #    operands are patterns or flags, not members (resolved against stored values later).
        mapped: dict[str, Any] = dict(filters)
        errors: list[str] = []
        for name, value in filters.items():
            allowed = enums.get(name)
            if allowed is None:
                continue
            if not isinstance(value, Mapping):
                mapped[name] = SearchHelpers.__enum_members(name, value, allowed, errors)
                continue
            op = FilterOperatorGrammar.operator_of(value)
            if op is None or op in PATTERN_OPS or op is FilterOp.EXISTS:
                continue
            operand = value[op.value]
            mapped[name] = {op.value: SearchHelpers.__enum_members(name, operand, allowed, errors)}
        return mapped, errors

    @staticmethod
    def title_field_spec(collection: Any, schema: Sequence[MetadataField]) -> MetadataField | None:
        """
        Resolve the collection's ``title_field`` name to its DOCUMENT-scope schema row.

        ``title_field`` is a soft reference (no FK): a name that no longer resolves to a
        document-scope field (renamed/deleted/chunk-scope) yields None, so hits fall back to the
        parser title instead of failing.

        Args:
            collection (Any): The collection row (its ``title_field`` may be absent or None).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            MetadataField | None: The display-title field row, or None when unset/unresolvable.
        """
        # 1. Unset → parser titles.
        name = getattr(collection, "title_field", None)
        if not name:
            return None
        # 2. Only a document-scope field can title a document.
        return next(
            (
                row
                for row in schema
                if row.field_name == name
                and getattr(row, "scope", FieldScope.DOCUMENT) == FieldScope.DOCUMENT
            ),
            None,
        )

    @staticmethod
    def to_hint_model(hint: FilterHint) -> SearchHint:
        """
        Map a resolver/zero-hit FilterHint onto its client model.

        Args:
            hint (FilterHint): The library-side hint.

        Returns:
            SearchHint: The client-facing hint.
        """
        # 1. Field-for-field copy (the client model is the wire contract).
        return SearchHint(
            field=hint.field,
            value=hint.value,
            message=hint.message,
            suggestions=list(hint.suggestions),
        )

    @staticmethod
    def _payload_type(field: MetadataField | None) -> PayloadType | None:
        """
        Resolve a field's Qdrant payload index type, defensively — None when unresolvable.

        Only an operator object needs a field's type, so this is looked up lazily (never for a
        plain scalar/list filter). A field object that carries no ``field_type`` (a lightweight
        stand-in shape) or an unmapped type yields None rather than raising — the grammar then
        reports a clean 422 instead of a 500.
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
    def operator_violations(
        filters: dict[str, Any] | None, schema: Sequence[MetadataField]
    ) -> list[str]:
        """
        Report operator-object filters (``{field: {"<op>": value}}``) a field cannot accept.

        Every operator object is validated against the field's payload index type by the shared
        ``FilterOperatorGrammar``: an unknown operator, an operator the type does not support (e.g.
        ``prefix`` on an integer), a forbidden combination (only range bounds combine), a malformed
        operand, or a range whose bound kind does not match the field (a datetime field needs
        ISO-8601 bounds, a numeric field numeric bounds). Non-filterable fields are the
        filterability gate's concern, not this check's.

        This runs on EVERY search, so it must never raise: a plain scalar/list filter is skipped
        untouched (its field type is never inspected).

        Args:
            filters (dict | None): The requested constraints (field → scalar, list, or operator
                object).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            list[str]: One human-readable message per problem (empty when all valid).
        """
        # 1. Index the FILTERABLE fields by name — typed lazily, only when an operator needs it.
        by_name = {row.field_name: row for row in schema if getattr(row, "filterable", False)}
        errors: list[str] = []
        for name, value in (filters or {}).items():
            # 2. Only an operator object is checked here; an unknown field is another gate's.
            if not isinstance(value, Mapping) or name not in by_name:
                continue
            ptype = SearchHelpers._payload_type(by_name[name])
            errors.extend(FilterOperatorGrammar.validate(name, value, ptype))
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
    def page_number(page: int | None) -> int | None:
        """Convert a stored 0-based page index into the 1-based page number a reader cites."""
        # 1. None (page-less) stays None; a real index — including 0 — shifts by one.
        return page + 1 if page is not None else None

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
            page_number=SearchHelpers.page_number(metadata.get("page")),
            bbox=metadata.get("bbox"),
            block_locations=[
                BlockLocationModel(
                    page=loc["page"],
                    page_number=SearchHelpers.page_number(loc["page"]),
                    bbox=loc["bbox"],
                )
                for loc in (metadata.get("block_locations") or [])
            ],
        )


__all__ = ["SearchHelpers"]
