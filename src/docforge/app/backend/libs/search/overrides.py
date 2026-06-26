# ====== Code Summary ======
# SearchOverridesHelpers — applies optional per-REQUEST search overrides onto a COPY of a
# collection's stored pipeline.search config (deep-merge of a few specific keys) WITHOUT
# mutating the persisted config, and validates that the overridden toggles have the providers
# they actually need. Powers the "Search Lab": tune retrieval live for a single query.
#
# Scope of the override surface (intentionally narrow):
#   vector_mode               -> pipeline.search.retrieve.vector_mode
#   fusion                    -> pipeline.search.retrieve.fusion
#   query_transform_strategy  -> pipeline.search.query_transform.strategy
#   rerank_enabled            -> pipeline.search.rerank.enabled
#
# Enum membership of the values is enforced upstream by the Pydantic SearchOverrides model
# (a bad value is a 422 request-validation error). This helper only handles the deep-merge
# and the *semantic* validation that an overridden toggle has a provider behind it — a toggle
# that would silently no-op (rerank on without a chain, query transform without an LLM) is a
# 422 here, never a silent degradation.

# ====== Standard Library Imports ======
from __future__ import annotations

import copy
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import ValidationError

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig
from common_libs.config.validation.validator.pipeline_checks import PipelineChecks


class SearchOverrideError(Exception):
    """
    Raised when per-request search overrides are semantically inadmissible.

    Distinct from the ``ValueError`` raised by ``build_search_pipeline`` (which means a
    provider could not be *built* — a 503): this means the caller asked for a capability the
    collection has not configured (a 422). The router translates it to an HTTP 422 with the
    precise message carried here.
    """


class SearchOverridesHelpers:
    """
    Static helpers that overlay per-request search overrides on a collection's pipeline.

    The collection's persisted ``pipeline`` dict is never mutated: ``apply`` works on a deep
    copy, ``validate`` only reads. Together they let the Search Lab tune retrieval for a single
    query without writing anything back.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchOverridesHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def __branch(parent: dict[str, Any], key: str) -> dict[str, Any]:
        """
        Return ``parent[key]`` as a dict, creating an empty one if absent or not a dict.

        Defensive against a stored pipeline where a search sub-block is missing or null.

        Args:
            parent (dict): Parent mapping to read/extend.
            key (str): Sub-key whose dict branch is needed.

        Returns:
            dict: The (possibly newly created) sub-dict, attached to ``parent``.
        """
        child = parent.get(key)
        if not isinstance(child, dict):
            child = {}
            parent[key] = child
        return child

    @classmethod
    def apply(cls, pipeline_dict: dict[str, Any] | None, overrides: dict[str, Any]) -> dict[str, Any]:
        """
        Deep-merge the provided override keys onto a COPY of the collection pipeline dict.

        Only the four supported override keys are mapped onto their pipeline.search paths; an
        absent override key leaves the stored value untouched. The input dict is never mutated.

        Args:
            pipeline_dict (dict | None): The collection's stored pipeline dict (may be None/empty).
            overrides (dict): Provided override keys (already filtered to non-None values).

        Returns:
            dict: A new pipeline dict with the overrides shadowing pipeline.search for this request.
        """
        # 1. Work on a deep copy so the persisted config is never touched.
        merged: dict[str, Any] = copy.deepcopy(pipeline_dict) if pipeline_dict else {}

        # 2. Resolve (or create) the search sub-branches the overrides target.
        search = cls.__branch(merged, "search")
        retrieve = cls.__branch(search, "retrieve")
        query_transform = cls.__branch(search, "query_transform")
        rerank = cls.__branch(search, "rerank")

        # 3. Map each provided override onto its specific pipeline.search path.
        if "vector_mode" in overrides:
            retrieve["vector_mode"] = overrides["vector_mode"]
        if "fusion" in overrides:
            retrieve["fusion"] = overrides["fusion"]
        if "query_transform_strategy" in overrides:
            query_transform["strategy"] = overrides["query_transform_strategy"]
        if "rerank_enabled" in overrides:
            rerank["enabled"] = overrides["rerank_enabled"]

        return merged

    @staticmethod
    def validate(merged_pipeline_dict: dict[str, Any]) -> None:
        """
        Reject overrides that would request an unconfigured provider (a silent no-op).

        Two semantic guards, both surfaced as 422 by the caller:
        - rerank turned on with an empty provider chain — reuses the shared ConfigValidator
          rule ``search.rerank.empty_chain`` so the Lab and the config-save path agree.
        - a non-passthrough query-transform strategy with no LLM provider configured.

        Args:
            merged_pipeline_dict (dict): Pipeline dict AFTER overrides were applied.

        Raises:
            SearchOverrideError: If an override needs a provider the collection has not configured.
        """
        # 1. Parse the merged pipeline so the typed search config can be inspected. Flipping an
        #    override on (e.g. rerank_enabled=true) can trigger coercion of a stored chain that was
        #    never validated while disabled; surface any resulting ValidationError as a 422 (a bad
        #    override request) rather than letting it bubble up as a 500.
        try:
            pipeline = PipelineConfig.from_dict(merged_pipeline_dict)
        except ValidationError as exc:
            raise SearchOverrideError(
                f"Override rejected: the resulting search config is invalid — {exc}"
            ) from exc
        search = pipeline.search

        # 2. Rerank coherence — reuse the shared empty_chain rule rather than re-implementing it.
        issues: list[dict[str, Any]] = []
        PipelineChecks.check_step_dependencies(pipeline, issues)
        if any(issue.get("code") == "search.rerank.empty_chain" for issue in issues):
            raise SearchOverrideError(
                "Override rerank_enabled=true rejected: this collection has no rerank provider "
                "configured (pipeline.search.rerank.chain is empty). Configure a reranker on the "
                "collection before enabling rerank for a query."
            )

        # 3. Query-transform coherence — a non-passthrough strategy needs an LLM provider.
        query_transform = search.query_transform
        if query_transform.strategy != "none" and query_transform.llm is None:
            raise SearchOverrideError(
                f"Override query_transform_strategy={query_transform.strategy!r} rejected: this "
                "collection has no LLM provider configured for query transformation "
                "(pipeline.search.query_transform.llm is unset). Configure an LLM on the "
                "collection before requesting a query transform."
            )


__all__ = ["SearchOverrideError", "SearchOverridesHelpers"]
