# ====== Code Summary ======
# MetaVectorSyncHelpers — the pure, I/O-free conventions the MetaVectorSyncFacade leans on: locate a
# collection's own embed node inside its serialised ingestion blob, rebuild that embedder from the
# registry (class + extra="forbid" config, so a drifted blob fails loudly — the same rebuild the
# search encode node does), and render a document-scope metadata value to the short text that gets
# embedded (a list joins with ", ", a scalar stringifies, empty renders to None). No store access
# here; the facade drives the embedder's hooks and writes to Qdrant.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver


class MetaVectorSyncHelpers:
    """Static, I/O-free helpers for rebuilding a collection's embedder and rendering meta values."""

    logger = loggerplusplus.bind(identifier="MetaVectorSyncHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetaVectorSyncHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def find_embed_node(cls, pipeline: dict[str, Any]) -> dict[str, Any] | None:
        """
        Locate the collection's embed node dict in its serialised ingestion blob (single-use).

        Args:
            pipeline (dict): The collection's stored ingestion pipeline blob.

        Returns:
            dict | None: The first embed-family node dict, or None when the collection has none.
        """
        # Delegate to the shared resolver — the embed family is single-use, so it returns THE one.
        return EmbedBlobResolver.find_embed_node(pipeline)

    @classmethod
    def rebuild_embedder(
        cls, embed_node: dict[str, Any]
    ) -> tuple[BaseEmbedderNode, BaseEmbedConfig]:
        """
        Rebuild the collection's embedder from its stored blob (class + re-validated config).

        Args:
            embed_node (dict): The embed-family node dict (its ``kind`` + ``config``).

        Returns:
            tuple[BaseEmbedderNode, BaseEmbedConfig]: A throwaway embedder instance (only its
                embedding hooks are exercised — never wired in a graph) and its validated config.

        Raises:
            pydantic.ValidationError: When the stored config drifted (extra="forbid" fails loudly).
        """
        # Delegate to the shared resolver, preserving this facade's throwaway-instance node id.
        return EmbedBlobResolver.rebuild(
            embed_node["kind"], embed_node.get("config", {}), node_id="meta_vector_embedder"
        )

    @staticmethod
    def render_value(value: Any) -> str | None:
        """
        Render a document-scope metadata value to the text embedded for its named vector.

        Mirrors the embed node's per-field rendering: a list joins with ", ", any scalar
        stringifies, and an empty/whitespace result is dropped (no vector for a blank value).

        Args:
            value (Any): The decoded document-scope metadata value (string, number or list).

        Returns:
            str | None: The text to embed, or None when the value renders to nothing.
        """
        text = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        return text if text.strip() else None


__all__ = ["MetaVectorSyncHelpers"]
