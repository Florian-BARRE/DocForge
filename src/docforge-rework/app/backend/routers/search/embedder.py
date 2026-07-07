# ====== Code Summary ======
# QueryEmbedder — turns a query STRING into the same vector shapes the collection's chunks were
# indexed with, using the collection's OWN embedder. It rebuilds the exact embed node from the
# stored blob (registry class + validated config, so a typo fails loudly) and drives its embedding
# hooks on a one-element batch — the node's public run() is built for whole chunk sets + a contract,
# which is far more machinery than a single query needs. Provider stays interchangeable: bge_server
# yields dense + sparse, an OpenAI-compatible endpoint yields dense only (sparse skipped gracefully).
# The embed config may carry an api_key — it is NEVER logged.

# ====== Standard Library Imports ======
from typing import cast

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
import shared_libs.pipelines.nodes.embed  # noqa: F401 — ensures every embedder self-registers
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.services.db.qdrant import SparseVec

# ====== Local Project Imports ======
from .helpers import EMBED_FAMILY


class QueryEmbedder(LoggerClass):
    """Embeds a query with a collection's own embedder — dense always, sparse when supported."""

    def __init__(self, blob: ActionNodeBlob) -> None:
        """
        Rebuild the collection's embed node from its serialised blob.

        Args:
            blob (ActionNodeBlob): The embed node's stored family/kind/config.

        Raises:
            KeyError: If no embedder is registered for the blob's kind.
            pydantic.ValidationError: If the stored config violates the node's Config model.
        """
        LoggerClass.__init__(self)
        # 1. Resolve the registered embedder class (bge_server, openai_compatible, …).
        node_class = cast(type[BaseEmbedderNode], NodeRegistry.get(EMBED_FAMILY, blob.kind))
        # 2. Re-validate the stored config (extra="forbid" — a drifted blob fails loudly).
        config = cast(BaseEmbedConfig, node_class.Config(**blob.config))
        # 3. A throwaway node instance — only its embedding hooks are exercised.
        self._node: BaseEmbedderNode = node_class(id="query_embed", config=config)
        self._config = config
        self.logger.debug(f"Query embedder ready (kind '{blob.kind}', sparse={config.embed_sparse})")

    async def __maybe_sparse(self, query: str) -> SparseVec | None:
        """The lexical vector — only when this embedder actually produces sparse vectors."""
        # 1. The collection may have indexed dense-only (or the provider has no sparse axis).
        if not self._config.embed_sparse:
            return None
        vectors = await self._node._embed_sparse([query])
        if not vectors:
            return None
        # 2. Adapt the pipeline's SparseVector to the store's SparseVec transfer type.
        vector = vectors[0]
        return SparseVec(indices=vector.indices, values=vector.values)

    async def embed(self, query: str) -> tuple[list[float], SparseVec | None]:
        """
        Embed the query into its dense (and, when supported, sparse) vector.

        Args:
            query (str): The query text.

        Returns:
            tuple[list[float], SparseVec | None]: The dense vector, and the sparse vector or None.
        """
        # 1. Dense — always (a query without a dense vector cannot be searched).
        dense = (await self._node._embed_dense([query]))[0]
        # 2. Sparse — only when the collection's embedder carries the lexical axis.
        sparse = await self.__maybe_sparse(query)
        return dense, sparse


__all__ = ["QueryEmbedder"]
