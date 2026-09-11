# ====== Code Summary ======
# The OpenAI-compatible embedder — dense vectors through any /v1/embeddings endpoint (OpenAI,
# vLLM, Infinity…) via the shared factory. The protocol has no sparse axis: the base skips it
# gracefully (dense-only collections).

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeUsage
from shared_libs.pipelines.nodes.openai_compat import (
    EndpointReachability,
    LangChainClientPool,
    OpenAICompatConfig,
    OpenAICompatHelpers,
)
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseEmbedConfig, BaseEmbedderNode


class EmbedOpenAICompatibleConfig(BaseEmbedConfig, OpenAICompatConfig):
    """OpenAI-compatible embeddings endpoint (endpoint fields inherited)."""


@NodeRegistry.register("embed")
class EmbedOpenAICompatibleNode(BaseEmbedderNode):
    """Dense embedding through any OpenAI-compatible /v1/embeddings endpoint."""

    KIND = "openai_compatible"
    NAME = "OpenAI-compatible embeddings"
    SUMMARY = "Dense vectors through any OpenAI-compatible embeddings endpoint."
    HOW_IT_WORKS = (
        "Sends the text batches to the endpoint's /v1/embeddings route through the shared "
        "factory. The protocol carries no sparse vectors — the sparse axis is skipped."
    )
    Config = EmbedOpenAICompatibleConfig
    UNIQUE_IN_GRAPH = True

    async def preflight(self) -> None:
        """Verify the endpoint exposes an OpenAI-compatible embeddings route, before any spend.

        Embedding goes through the openai SDK, which POSTs to ``{base_url}/embeddings``. A plain
        reachability probe is NOT enough: a TEI-only server (e.g. bge_server, whose routes are
        ``/embed`` / ``/embed_sparse``) answers on the host yet has no ``/embeddings`` route, so it
        would pass a reachability check and only 404 mid-run — after the pipeline already spent.
        Probing the actual embeddings route turns that into an actionable fail-fast.
        """
        config: EmbedOpenAICompatibleConfig = self.config
        await EndpointReachability.check_route_present(
            node_kind=self.KIND,
            base_url=config.base_url,
            path="/embeddings",
            capability_hint=(
                "this node needs an OpenAI-compatible /v1/embeddings endpoint; this looks like a "
                "TEI-only server (its routes are /embed, not /embeddings). Point base_url at an "
                "OpenAI-compatible embeddings endpoint (e.g. a base_url ending in /v1), or use the "
                "embed/bge_server node for a TEI/bge_server host"
            ),
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via the factory-built embeddings client, capturing paid token usage.

        Calls the underlying OpenAI-SDK embeddings resource directly (rather than LangChain's
        ``aembed_documents``, which discards usage) so the per-call ``usage.prompt_tokens`` can be
        folded into the node's running total for the post-hoc cost meter. The base node already caps
        the batch size and disables the ctx-length check, so a single ``create`` over the batch mirrors
        the prior behaviour; ``.data`` is re-sorted by index to keep the 1:1 order the caller expects.
        """
        config: EmbedOpenAICompatibleConfig = self.config
        # The pooled client self-heals a dead socket left by an endpoint restart (connect-phase error
        # → evict + retry once on a fresh client); the batch is already capped by the base node.
        response = await LangChainClientPool.arun(
            lambda: OpenAICompatHelpers.embeddings(config),
            lambda client: client.async_client.create(input=texts, model=config.model),
            label=f"embed '{self.KIND}'",
        )
        self._accumulate_usage(response, config.model)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]

    def _accumulate_usage(self, response: object, model: str) -> None:
        """Fold one embeddings response's input-token usage into the node's running total.

        An embeddings call bills input tokens only, so it maps onto ``NodeUsage`` as
        ``prompt_tokens=<input tokens>, completion_tokens=0``. Defensive like
        ``NodeUsage.from_usage_metadata``: a missing/odd usage payload is ignored (leaves the total
        unchanged, never fails the node), so a paid embed still emits vectors even if its endpoint
        omits usage — it just contributes no billable tokens.

        Args:
            response (object): The embeddings API response (carries ``usage.prompt_tokens`` /
                ``usage.total_tokens`` on an OpenAI-compatible endpoint).
            model (str): The configured embedding model id — the key into the embed pricing table.
        """
        usage = getattr(response, "usage", None)
        raw_tokens = getattr(usage, "prompt_tokens", None)
        if raw_tokens is None:
            raw_tokens = getattr(usage, "total_tokens", None)
        try:
            tokens = int(raw_tokens)
        except (TypeError, ValueError):
            return
        prior = self._last_usage.prompt_tokens if self._last_usage is not None else 0
        self._last_usage = NodeUsage(model=model, prompt_tokens=prior + tokens, completion_tokens=0)


__all__ = ["EmbedOpenAICompatibleNode", "EmbedOpenAICompatibleConfig"]
