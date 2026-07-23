# ====== Code Summary ======
# MetaVectorSyncHelpers — the pure, I/O-free conventions the MetaVectorSyncFacade leans on: locate a
# collection's own embed node inside its serialised ingestion blob, rebuild that embedder from the
# registry (class + extra="forbid" config, so a drifted blob fails loudly — the same rebuild the
# search encode node does), and render a document-scope metadata value to the short text that gets
# embedded (a list joins with ", ", a scalar stringifies, empty renders to None). No store access
# here; the facade drives the embedder's hooks and writes to Qdrant.

# ====== Standard Library Imports ======
from collections.abc import Iterator
from typing import Any, cast

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
import shared_libs.pipelines.nodes.embed  # noqa: F401 — ensures every embedder self-registers
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry

# The registry family every embedder self-registers under (never string-literalled elsewhere).
_EMBED_FAMILY = "embed"


class MetaVectorSyncHelpers:
    """Static, I/O-free helpers for rebuilding a collection's embedder and rendering meta values."""

    logger = loggerplusplus.bind(identifier="MetaVectorSyncHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetaVectorSyncHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def __iter_action_blobs(cls, blob: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield every action-node dict in a (possibly nested) group/foreach pipeline blob."""
        # 1. A foreach wraps a single group body — descend into it.
        if "body" in blob:
            yield from cls.__iter_action_blobs(blob["body"])
        # 2. A group holds children — descend into each.
        elif "nodes" in blob:
            for child in blob["nodes"]:
                yield from cls.__iter_action_blobs(child)
        # 3. A leaf action carries a family — it is what we iterate over.
        elif blob.get("family"):
            yield blob

    @classmethod
    def find_embed_node(cls, pipeline: dict[str, Any]) -> dict[str, Any] | None:
        """
        Locate the collection's embed node dict in its serialised ingestion blob (single-use).

        Args:
            pipeline (dict): The collection's stored ingestion pipeline blob.

        Returns:
            dict | None: The first embed-family node dict, or None when the collection has none.
        """
        # The embed family is single-use, so the first embed node is THE one.
        for node in cls.__iter_action_blobs(pipeline):
            if node.get("family") == _EMBED_FAMILY:
                return node
        return None

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
        # 1. Resolve the registered embedder class (bge_server, openai_compatible, …).
        node_class = cast(
            type[BaseEmbedderNode], NodeRegistry.get(_EMBED_FAMILY, embed_node["kind"])
        )
        # 2. Re-validate the stored config (extra="forbid" — a drifted blob fails loudly).
        config = cast(BaseEmbedConfig, node_class.Config(**embed_node.get("config", {})))
        # 3. A throwaway instance — only its embedding hooks are exercised.
        return node_class(id="meta_vector_embedder", config=config), config

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
