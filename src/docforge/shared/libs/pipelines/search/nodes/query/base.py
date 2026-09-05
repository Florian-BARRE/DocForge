# ====== Code Summary ======
# BaseQueryLlmNode + BaseQueryLlmConfig — the shared spine of the query-understanding LLM methods
# (rewrite, HyDE). Both make ONE bounded, degrading chat-completions call on a per-collection
# provider endpoint and fold the answer back into the QuerySpec; they differ ONLY in their prompt
# and in how they fold the model's text (the two abstract hooks). The base owns the provider config
# shape, the wall-clock-capped call, the token-usage capture and — critically — the DEGRADE
# DISCIPLINE: on ANY provider error it returns the ORIGINAL QuerySpec unchanged, so an enabled
# query transform can NEVER break a search (worst case: the query runs un-transformed).
#
# Being abstract (via _prompt/_fold), this class is not registered and skips the ActionNode strict
# interface check; the concrete rewrite/hyde nodes implement the two hooks and declare their KIND.

# ====== Standard Library Imports ======
import asyncio
from abc import abstractmethod

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeInput, NodeOutput, NodeUsage, TimeoutConfig
from shared_libs.pipelines.nodes.openai_compat import (
    EndpointReachability,
    OpenAICompatConfig,
    OpenAICompatHelpers,
)
from shared_libs.public_models.search import QuerySpec

# Provider-hosted defaults: the node is OFF by default (never in the stock blob), so these only fill
# an opt-in blob's empty config until the user sets the real per-collection provider values.
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"

# The reserved QuerySpec.flags key a degraded query transform stamps its notice under. It rides the
# spec downstream to the encode node, which folds it into EncodedQuery.degraded → SearchResult.debug
# so a caller SEES that the provider degraded and the raw query was used (never a silent fallback).
QUERY_DEGRADED_FLAG = "query_degraded"


class BaseQueryLlmConfig(TimeoutConfig):
    """Provider endpoint + generation knobs shared by the query-understanding LLM methods.

    Mixes in ``TimeoutConfig`` for the shared network-timeout surface — notably
    ``preflight_timeout_seconds``, the budget for the pre-spend reachability probe the
    collection-health / preflight sweep runs against the provider endpoint (see ``preflight``)."""

    base_url: str = Field(
        default=_DEFAULT_BASE_URL,
        description="OpenAI-compatible chat endpoint. Provider-hosted — set per collection in the "
        "search blob (the node is OFF by default, so this default is never reached out-of-box).",
    )
    # api_key is masked on read / restored on write by the collection router's search-blob
    # redact/restore (it already handles search-blob provider secrets) — never surfaced in clear.
    api_key: str = Field(default="", description="Bearer token for the endpoint (may be empty).")
    model: str = Field(default=_DEFAULT_MODEL, description="Model name served by the endpoint.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=256, ge=1, description="Maximum tokens to generate.")
    timeout_seconds: float = Field(default=30.0, gt=0.0, description="Per-request timeout (s).")
    degrade_after_seconds: float = Field(
        default=8.0,
        gt=0.0,
        description="Wall-clock cap (seconds) on the provider call, bounded WELL BELOW the ~30 s "
        "search run cap. A slow/cold provider is given up on here (a catchable Exception) and the "
        "search proceeds with the ORIGINAL query rather than sinking to the run cap (a 504).",
    )


class QueryLlmConsumes(NodeInput):
    """Input: the normalised query to transform."""

    spec: QuerySpec = Field(description="The normalised query to transform.")


class QueryLlmProduces(NodeOutput):
    """Output: the transformed query — the original spec, unchanged, on any provider failure."""

    spec: QuerySpec = Field(
        description="The transformed query (all non-text fields copied through; unchanged on degrade)."
    )


class BaseQueryLlmNode(ActionNode):
    """Abstract base: one bounded, degrading chat call folded back into the QuerySpec."""

    Config = BaseQueryLlmConfig
    Consumes = QueryLlmConsumes
    Produces = QueryLlmProduces
    UNIQUE_IN_GRAPH = True

    async def preflight(self) -> None:
        """Verify the query-LLM endpoint is reachable and its credentials accepted, before any spend.

        Gives the search-side query providers (rewrite / HyDE) the SAME reachability coverage the
        ingest providers have: the collection-health / preflight sweep probes only leaves that
        OVERRIDE this hook, so without it a configured-but-unreachable rewrite/HyDE endpoint stayed
        invisible to a health check (its failure only ever surfaced as a silent run-time degrade).
        Reads ``self.config`` only, so the app's on-demand sweep can call it with no run wiring.
        """
        config: BaseQueryLlmConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    def __with_degrade_flag(self, spec: QuerySpec) -> QuerySpec:
        """
        Copy the spec with a degrade notice merged into its flags (idempotent, additive).

        The notice names THIS transform's kind so a caller sees exactly which query provider degraded.
        A pre-existing notice (a second query transform degraded upstream) is preserved by appending,
        so no degrade signal is ever overwritten.

        Args:
            spec (QuerySpec): The original query returned unchanged on degrade.

        Returns:
            QuerySpec: The same query with ``flags[QUERY_DEGRADED_FLAG]`` carrying the notice.
        """
        # 1. Compose this transform's notice and merge it with any note an upstream transform left.
        note = f"query {self.KIND} unavailable — provider degraded, raw query used"
        existing = spec.flags.get(QUERY_DEGRADED_FLAG)
        merged = f"{existing}; {note}" if existing else note
        return spec.model_copy(update={"flags": {**spec.flags, QUERY_DEGRADED_FLAG: merged}})

    async def run(self, data: QueryLlmConsumes) -> QueryLlmProduces:
        """
        Make one bounded chat call and fold its answer into the spec, degrading to the original.

        Args:
            data (QueryLlmConsumes): The normalised query to transform.

        Returns:
            QueryLlmProduces: The transformed query, or the ORIGINAL spec on any provider failure.
        """
        config: BaseQueryLlmConfig = self.config
        endpoint = OpenAICompatConfig(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
        )
        model = OpenAICompatHelpers.chat(
            endpoint, temperature=config.temperature, max_tokens=config.max_tokens
        )

        # The degrade seam: bound the call under the run cap. Catch Exception so a timeout/provider
        # error falls back to the original query — never a raise. CancelledError (the run's own
        # wall-clock cap) is NOT an Exception, so it still propagates and becomes the timeout path.
        try:
            answer = await asyncio.wait_for(
                model.ainvoke(self._prompt(data.spec)), timeout=config.degrade_after_seconds
            )
        except Exception as exc:
            self.logger.warning(
                f"Query '{self.KIND}' degraded ({type(exc).__name__}: {exc}) — using the "
                "original query un-transformed"
            )
            # Return the ORIGINAL query, but stamp a degrade notice into its flags so the fallback is
            # VISIBLE downstream (encode folds it into SearchResult.debug) rather than silent.
            return self.Produces(spec=self.__with_degrade_flag(data.spec))

        # Fold the answer back into the spec (each method decides how; empty answer → original spec).
        output = self.Produces(spec=self._fold(data.spec, str(getattr(answer, "content", ""))))
        # The call was paid even when the fold degraded to the original — stamp its usage.
        output._usage = NodeUsage.from_usage_metadata(
            getattr(answer, "usage_metadata", None), config.model
        )
        return output

    @abstractmethod
    def _prompt(self, spec: QuerySpec) -> list[tuple[str, str]]:
        """
        Build the chat messages for this transform.

        Args:
            spec (QuerySpec): The query being transformed.

        Returns:
            list[tuple[str, str]]: (role, content) message tuples for the chat model.
        """
        ...

    @abstractmethod
    def _fold(self, spec: QuerySpec, answer: str) -> QuerySpec:
        """
        Fold the model's answer back into the spec (an empty answer degrades to the original).

        Args:
            spec (QuerySpec): The incoming query.
            answer (str): The model's raw completion text.

        Returns:
            QuerySpec: The updated spec, or ``spec`` unchanged when the answer is empty.
        """
        ...


__all__ = [
    "BaseQueryLlmConfig",
    "QueryLlmConsumes",
    "QueryLlmProduces",
    "BaseQueryLlmNode",
    "QUERY_DEGRADED_FLAG",
]
