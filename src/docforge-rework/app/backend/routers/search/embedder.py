# ====== Code Summary ======
# QueryEmbedder — the collection's late-interaction CAPABILITY probe for the search route. It rebuilds
# the exact embed node from the stored blob (registry class + validated config, so a typo fails
# loudly) and reports whether that embedder emits a ColBERT axis. This mirrors the flag the ingest
# side read, so a query only asks for a ColBERT re-score when the chunks were actually indexed with
# one. The actual query encoding is the search graph's job (the encode node), not this seam. The
# api_key is NEVER logged.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.pipelines.nodes.embed.base import BaseEmbedderNode
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver


class QueryEmbedder(LoggerClass):
    """Probes a collection's own embedder for the ColBERT (late-interaction) capability."""

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
        # A throwaway embedder instance — only its capability flag is read (never wired in a graph).
        self._node: BaseEmbedderNode = EmbedBlobResolver.rebuild(
            blob.kind, blob.config, node_id="query_embed"
        )[0]
        self.logger.debug(f"Query embedder probe ready (kind '{blob.kind}')")

    def wants_colbert(self) -> bool:
        """
        Whether this collection's embedder produces the ColBERT axis.

        This is the collection's single source of truth for late interaction — it mirrors the same
        flag the ingest side reads, so a query only asks for a ColBERT vector when the chunks were
        actually indexed with one (the graceful-guard signal, no extra Qdrant round-trip).

        Returns:
            bool: True when the embedder is configured to emit ColBERT multi-vectors.
        """
        return self._node._wants_colbert()


__all__ = ["QueryEmbedder"]
