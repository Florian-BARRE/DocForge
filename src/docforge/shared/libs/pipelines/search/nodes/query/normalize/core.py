# ====== Code Summary ======
# The query-normalize node — the free, zero-model query-intake method: it trims and case-folds the
# raw query text, carries the caller's filter map and flags through, and sizes the retrieval depth
# (top_k from the caller, candidate_k as an over-sample so rerank/post-process have a pool to work
# on). Pure and deterministic — no store, no model. It is the entry node of the default search graph.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import (
    CONTENT_FIELD,
    QueryFilters,
    QuerySpec,
    RawQuery,
    SearchTarget,
    default_content_targets,
)


class QueryNormalizeConfig(NodeConfig):
    """The over-sampling knobs of the retrieval depth (no model, no store)."""

    content_modalities: Literal["hybrid", "semantic", "lexical"] = Field(
        default="hybrid",
        description="Which content axes a query with NO explicit search_targets searches. 'hybrid' "
        "(default) — both the dense (semantic) and sparse (lexical) content vectors, fused. "
        "'semantic' — the dense vector only (a dense-only collection, or a pure-meaning setup). "
        "'lexical' — the sparse BM25 vector only. This shapes ONLY the default when the caller sends "
        "no targets; an explicit per-query targets list always wins. The collection's embedder still "
        "decides which axes actually exist, so selecting an unindexed axis degrades gracefully.",
    )
    fold_case: bool = Field(
        default=False,
        description="Lower-case the query text. OFF by default: documents are embedded from their "
        "original-case text, so BGE-M3's tokenizer (dense AND sparse) sees mixed case on the doc "
        "side; folding only the query would put query and document vectors in slightly different "
        "spaces and cost recall. Turn on only for a pure-lexical setup that also lower-cases docs.",
    )
    candidate_multiplier: int = Field(
        default=4,
        gt=0,
        le=100,
        description="candidate_k = top_k × this (the retrieval over-sample factor). Capped at 100: "
        "beyond that candidate_k = top_k × multiplier explodes the retrieval pool with no recall "
        "benefit (rerank/post-process saturate well before).",
    )
    candidate_floor: int = Field(
        default=100, gt=0, description="Minimum candidate_k, so a small top_k still yields a pool."
    )


class QueryNormalizeConsumes(NodeInput):
    """Input: the caller's raw query and filter map (both from the run input)."""

    query: RawQuery = Field(description="The caller's raw query (text, top_k, flags).")
    filters: QueryFilters = Field(description="The caller's raw field → value filter map.")


class QueryNormalizeProduces(NodeOutput):
    """Output: the normalised, retrieval-ready query."""

    spec: QuerySpec = Field(description="The normalised QuerySpec the encode/retrieve stages read.")


@NodeRegistry.register("query")
class QueryNormalizeNode(ActionNode):
    """Normalise the raw query into a retrieval-ready QuerySpec (trim/fold + depth sizing)."""

    KIND = "normalize"
    NAME = "Normalize query"
    SUMMARY = "Trim the query (case preserved), structure filters, and size the retrieval depth."
    HOW_IT_WORKS = (
        "Strips the query text (case preserved by default, to match the original-case documents), "
        "carries the filter map and flags through, keeps the caller's top_k and derives candidate_k "
        "as an over-sampled pool (max(top_k × multiplier, floor)). Zero model, zero store — the free "
        "query-intake method."
    )
    Config = QueryNormalizeConfig
    Consumes = QueryNormalizeConsumes
    Produces = QueryNormalizeProduces

    def __default_targets(self) -> list[SearchTarget]:
        """Build the content-target default for a target-less query from the configured modalities.

        ``hybrid`` keeps the historical both-axes default; ``semantic``/``lexical`` narrow it to the
        dense or sparse content vector so a preset (e.g. dense-only) can shape plain-query behaviour
        without a new node. The collection's embedder still decides which axes truly exist.
        """
        config: QueryNormalizeConfig = self.config
        if config.content_modalities == "hybrid":
            return default_content_targets()
        return [
            SearchTarget(
                field=CONTENT_FIELD,
                semantic=config.content_modalities == "semantic",
                lexical=config.content_modalities == "lexical",
            )
        ]

    async def run(self, data: QueryNormalizeConsumes) -> QueryNormalizeProduces:
        """
        Normalise the raw query into a QuerySpec.

        Args:
            data (QueryNormalizeConsumes): The caller's raw query and filter map.

        Returns:
            QueryNormalizeProduces: The retrieval-ready QuerySpec.
        """
        config: QueryNormalizeConfig = self.config
        # 1. Clean the query text — trim always, case-fold when configured.
        text = data.query.text.strip()
        if config.fold_case:
            text = text.lower()

        # 2. Size the retrieval depth: honour the caller's top_k, over-sample the candidate pool.
        top_k = data.query.top_k
        candidate_k = max(top_k * config.candidate_multiplier, config.candidate_floor)

        # 3. Carry the caller's field × modality selection through; an empty list falls back to the
        #    configured content default so a spec never reaches retrieval with zero targets to search.
        targets = list(data.query.search_targets) or self.__default_targets()

        # 4. Assemble the retrieval-ready spec (filters/flags carried through untouched).
        spec = QuerySpec(
            text=text,
            filters=dict(data.filters.filters),
            top_k=top_k,
            candidate_k=candidate_k,
            search_targets=targets,
            flags=dict(data.query.flags),
        )
        self.logger.debug(f"Normalized query (top_k={top_k}, candidate_k={candidate_k})")
        return QueryNormalizeProduces(spec=spec)


__all__ = [
    "QueryNormalizeNode",
    "QueryNormalizeConfig",
    "QueryNormalizeConsumes",
    "QueryNormalizeProduces",
]
