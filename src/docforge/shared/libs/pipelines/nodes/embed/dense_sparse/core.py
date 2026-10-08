# ====== Code Summary ======
# The ``(embed, dense_sparse)`` node — THE embedder: a dense provider slot and a sparse provider slot,
# chosen independently (three modes: dense only, sparse only, dense + sparse). When both slots resolve
# to the SAME endpoint of a provider that serves both axes in one call (bge_server /embed_all), each
# batch is ONE combined request under ONE limiter slot; otherwise the two axes run concurrently per
# batch, each with its own endpoint policy (retry/backoff/concurrency cap). The sparse slot also
# declares whether its vectors need the store's IDF modifier (bm25_local) — the vector schema and the
# metadata/query encoders all follow this one slot. Provider HTTP happens in-node; no store I/O.

# ====== Standard Library Imports ======
from urllib.parse import urlsplit

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import EndpointKey, NodeUsage
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SparseVector

# ====== Local Project Imports ======
from ..base import BaseEmbedderNode, EmbedCallPolicy, EmbedConsumes, EmbedProduces
from ..providers import EmbedProvider, EmbedProviderRegistry, EmbedRole
from .config import EmbedDenseSparseConfig


@NodeRegistry.register("embed")
class EmbedDenseSparseNode(BaseEmbedderNode):
    """Dense + sparse vectors from two independent provider slots (combined when one server)."""

    KIND = "dense_sparse"
    NAME = "Dense + sparse embedder"
    SUMMARY = "Pick a dense provider and a sparse provider independently (either may be off)."
    HOW_IT_WORKS = (
        "Each chunk's enriched text is encoded by the dense slot (bge_server / openai_compatible) "
        "and the sparse slot (bge_server learned weights / bm25_local in-process BM25). Both slots on "
        "the same bge_server → one /embed_all call per batch; different servers → the two calls run "
        "concurrently, each under its own endpoint's retry and concurrency policy."
    )
    Config = EmbedDenseSparseConfig
    # A failure-only fallback chain of embedders is legitimate repetition (a legacy bge_server →
    # openai_compatible chain migrates to two dense_sparse steps), so the kind is not single-use.
    UNIQUE_IN_GRAPH = False

    def __init__(self, id: str, config: EmbedDenseSparseConfig) -> None:
        """
        Args:
            id (str): Graph-unique identifier this node is wired under.
            config (EmbedDenseSparseConfig): The two provider slots + shared knobs.
        """
        super().__init__(id, config)
        self.__dense = EmbedProviderRegistry.build(config.dense) if config.dense else None
        self.__sparse = EmbedProviderRegistry.build(config.sparse) if config.sparse else None

    @staticmethod
    def __endpoint_identity(url: str) -> str:
        """``scheme://host:port/path`` — two spellings of the same route compare equal."""
        path = urlsplit(url.strip()).path.rstrip("/")
        return f"{EndpointKey.normalize(url)}{path}"

    def __providers(self) -> list[EmbedProvider]:
        """The configured providers (one entry per non-null slot)."""
        return [provider for provider in (self.__dense, self.__sparse) if provider is not None]

    def combined(self) -> bool:
        """Whether both axes come from ONE call: same kind, combined-capable, same endpoint."""
        dense, sparse = self.__dense, self.__sparse
        return (
            dense is not None
            and sparse is not None
            and dense.KIND == sparse.KIND
            and dense.SUPPORTS_COMBINED
            and bool(dense.endpoint)
            and self.__endpoint_identity(dense.endpoint)
            == self.__endpoint_identity(sparse.endpoint)
        )

    def has_dense(self) -> bool:
        """True when the dense slot is set."""
        return self.__dense is not None

    def has_sparse(self) -> bool:
        """True when the sparse slot is set."""
        return self.__sparse is not None

    def sparse_idf(self) -> bool:
        """True when the sparse provider emits term frequencies scored with the store's IDF."""
        return self.__sparse is not None and self.__sparse.SPARSE_IDF

    def model_name(self) -> str:
        """The dense model (the vector space identity), else the sparse encoding."""
        provider = self.__dense or self.__sparse
        return provider.config.model if provider is not None else ""

    def probe_endpoints(self) -> list[str]:
        """The distinct remote endpoints the slots call (the egress/preflight surface)."""
        seen: dict[str, str] = {}
        for provider in self.__providers():
            if provider.endpoint:
                seen.setdefault(self.__endpoint_identity(provider.endpoint), provider.endpoint)
        return list(seen.values())

    def _call_policy(self, axis: str) -> EmbedCallPolicy:
        """The sparse slot's policy for sparse calls; the dense slot's for dense AND combined."""
        provider = self.__sparse if axis == "sparse" else self.__dense
        return EmbedCallPolicy.from_config(provider.config if provider is not None else None)

    def _parallel_axes(self) -> bool:
        """Independent slots: the two axis calls of a batch run concurrently."""
        return True

    def _collect_usage(self) -> NodeUsage | None:
        """Merge the slots' paid-call usage (a local/free provider contributes nothing)."""
        usages = [p.usage for p in self.__providers() if p.usage is not None]
        if not usages:
            return None
        return NodeUsage(
            model=usages[0].model,
            prompt_tokens=sum(u.prompt_tokens for u in usages),
            completion_tokens=0,
        )

    def preflight_budget_seconds(self) -> float:
        """Worst-case wall-clock of ``preflight()``: each distinct endpoint's probe, run in turn."""
        budgets: dict[str, float] = {}
        for provider in self.__providers():
            if provider.endpoint:
                timeout = getattr(provider.config, "preflight_timeout_seconds", None)
                budgets.setdefault(
                    self.__endpoint_identity(provider.endpoint),
                    EndpointReachability.budget(timeout)
                    if timeout
                    else EndpointReachability.budget(),
                )
        return sum(budgets.values()) or EndpointReachability.budget()

    async def preflight(self) -> None:
        """Probe each DISTINCT remote endpoint once, before any spend (in-process slots skip)."""
        probed: set[str] = set()
        for provider in self.__providers():
            identity = self.__endpoint_identity(provider.endpoint) if provider.endpoint else ""
            if identity and identity not in probed:
                probed.add(identity)
                await provider.preflight()

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors from the dense slot."""
        if self.__dense is None:
            raise RuntimeError("this embedder has no dense slot")
        return await self.__dense.embed_dense(texts)

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Content sparse vectors from the sparse slot (None when the slot is off)."""
        return await self.__sparse.embed_sparse(texts, EmbedRole.CONTENT) if self.__sparse else None

    async def _embed_sparse_fields(self, texts: list[str]) -> list[SparseVector] | None:
        """Metadata-value sparse vectors from the SAME sparse slot (field-length normalisation)."""
        return await self.__sparse.embed_sparse(texts, EmbedRole.FIELD) if self.__sparse else None

    async def _embed_query_sparse(self, text: str) -> SparseVector | None:
        """The query's sparse vector from the sparse slot's query-side encoding."""
        return await self.__sparse.embed_query_sparse(text) if self.__sparse else None

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """ONE combined call when both slots are the same server — else None (two calls)."""
        if not self.combined():
            return None
        return await self.__dense.embed_dense_sparse(texts)  # type: ignore[union-attr]

    async def run(self, data: EmbedConsumes) -> EmbedProduces:
        """Reset the slots' usage tallies, then run the shared embed frame."""
        for provider in self.__providers():
            provider.usage = None
        return await super().run(data)


__all__ = ["EmbedDenseSparseNode"]
