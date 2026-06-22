# ====== Code Summary ======
# QueryTransformStage — applies LLM-based query expansion or rewriting before retrieval.
# Strategy "none" is a no-op passthrough.  "rewrite" and "hyde" produce one variant;
# "multi_query" produces n_variants reformulations for RRF-based multi-query retrieval.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.config.pipeline.stages.search_config import QueryTransformConfig
from libs.providers.llm.base import LLMProvider

# ─── Prompt templates ──────────────────────────────────────────────────────────

REWRITE_PROMPT = (
    "You are a search query optimizer. Rewrite the following query to be more specific "
    "and search-friendly. Output ONLY the rewritten query, no explanation.\n\n"
    "Query: {query}\n\nRewritten query:"
)

HYDE_PROMPT = (
    "Write a detailed passage that directly answers the following question. "
    "Be specific and factual.\n\n"
    "Question: {query}\n\nPassage:"
)

MULTI_QUERY_PROMPT = (
    "Generate {n} diverse search query reformulations of the following query. "
    "Each reformulation should approach the topic from a different angle. "
    "Output ONLY the queries, one per line, no numbering or bullets.\n\n"
    "Query: {query}\n\nReformulations:"
)


class QueryTransformStage(LoggerClass):
    """
    LLM-powered query transformation stage.

    Transforms a user query into one or more variants before retrieval.
    When strategy is "none" or no LLM is provided, the query is returned unchanged.

    Strategies:
    - ``"none"``: passthrough — returns ``[query]`` unchanged.
    - ``"rewrite"``: LLM rewrites the query to be more search-friendly.
    - ``"hyde"``: LLM generates a hypothetical answer passage (HyDE method).
    - ``"multi_query"``: LLM produces n_variants reformulations for RRF fusion.

    Attributes:
        _config (QueryTransformConfig): Strategy and variant count.
        _llm (LLMProvider | None): LLM provider instance (None = passthrough).
    """

    def __init__(
        self,
        config: QueryTransformConfig,
        llm: LLMProvider | None = None,
    ) -> None:
        """
        Initialize the query transform stage.

        Args:
            config (QueryTransformConfig): Strategy and parameter settings.
            llm (LLMProvider | None): LLM provider for transform strategies.
                When None, all strategies behave as "none" (passthrough).
        """
        LoggerClass.__init__(self)
        self._config = config
        self._llm = llm
        self.logger.debug(
            f"QueryTransformStage: strategy={self._config.strategy} "
            f"llm={'set' if self._llm else 'none'}"
        )

    async def run(self, query: str) -> list[str]:
        """
        Apply the configured transform and return query variants.

        Returns ``[query]`` unchanged when strategy is "none" or llm is None.
        The original query is always included as a fallback variant in case the
        LLM produces no usable output.

        Args:
            query (str): The original user search query.

        Returns:
            list[str]: One or more query strings for retrieval (at least ``[query]``).
        """
        # 1. Passthrough — no LLM needed
        if self._config.strategy == "none" or self._llm is None:
            return [query]

        self.logger.debug(f"QueryTransform: strategy={self._config.strategy} query={query[:60]!r}…")

        # 2. Dispatch to the appropriate transform strategy
        try:
            if self._config.strategy == "rewrite":
                return await self._rewrite(query)
            if self._config.strategy == "hyde":
                return await self._hyde(query)
            if self._config.strategy == "multi_query":
                return await self._multi_query(query)
        except Exception as exc:
            # LLM failures degrade gracefully — fall back to the original query
            self.logger.warning(f"QueryTransform: LLM call failed, using original query — {exc}")

        return [query]

    async def _rewrite(self, query: str) -> list[str]:
        """
        Rewrite the query to be more specific and search-friendly.

        Args:
            query (str): Original query.

        Returns:
            list[str]: ``[rewritten_query]``, falling back to ``[query]`` if output is empty.
        """
        prompt = REWRITE_PROMPT.format(query=query)
        result = (await self._llm.generate(prompt, max_tokens=128, temperature=0.0)).strip()
        return [result] if result else [query]

    async def _hyde(self, query: str) -> list[str]:
        """
        Generate a hypothetical answer passage that describes the ideal search result.

        Args:
            query (str): Original query.

        Returns:
            list[str]: ``[hypothetical_passage]``.
        """
        prompt = HYDE_PROMPT.format(query=query)
        result = (await self._llm.generate(prompt, max_tokens=256, temperature=0.3)).strip()
        return [result] if result else [query]

    async def _multi_query(self, query: str) -> list[str]:
        """
        Generate n_variants reformulations of the query for RRF fusion.

        Args:
            query (str): Original query.

        Returns:
            list[str]: List of reformulations (always includes the original query as a fallback).
        """
        prompt = MULTI_QUERY_PROMPT.format(n=self._config.n_variants, query=query)
        result = (await self._llm.generate(prompt, max_tokens=256, temperature=0.7)).strip()

        # 3. Parse one query per line; filter empty lines
        lines = [line.strip() for line in result.splitlines() if line.strip()]
        variants = lines[:self._config.n_variants]

        # 4. Always include the original query as a reliable fallback
        if query not in variants:
            variants.append(query)

        return variants if variants else [query]
