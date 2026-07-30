# ====== Code Summary ======
# EmbedBlobResolver — the single, store-free way to pull a collection's OWN embedder out of its
# serialised pipeline blob and rebuild it. It walks the possibly-nested group/foreach topology to
# find the first embed-family node (the family is single-use, so the first IS the one), then
# re-instantiates the registered embedder class with its stored config (extra="forbid", so a
# drifted blob fails loudly). Consolidates the copy-pasted blob walker + registry rebuild that the
# search encode node, the search contract builder, the query-embedder probe, and the meta-vector
# sync facade each carried. No store access here — the caller drives the embedder's hooks.

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


class EmbedBlobResolver:
    """Static, store-free resolver: find a collection's embed node in its blob and rebuild it."""

    logger = loggerplusplus.bind(identifier="EmbedBlobResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EmbedBlobResolver is a static-only class and cannot be instantiated.")

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
        Locate a collection's embed node dict in its serialised pipeline blob (single-use).

        Args:
            pipeline (dict): The collection's stored pipeline blob (a serialised group topology,
                possibly nesting foreach bodies and sub-groups).

        Returns:
            dict | None: The first embed-family node dict, or None when the blob carries none.
        """
        # The embed family is single-use, so the first embed node is THE one.
        for node in cls.__iter_action_blobs(pipeline):
            if node.get("family") == _EMBED_FAMILY:
                return node
        return None

    @classmethod
    def rebuild(
        cls, kind: str, config: dict[str, Any], *, node_id: str = "embedder"
    ) -> tuple[BaseEmbedderNode, BaseEmbedConfig]:
        """
        Rebuild an embedder from a stored blob (registry class + re-validated config).

        The embedder is a throwaway instance — only its embedding/capability hooks are exercised;
        it is never wired into a graph.

        Args:
            kind (str): The embed node's kind (the registry key within the embed family).
            config (dict): The embed node's stored config, re-validated (extra="forbid").
            node_id (str): The id given to the throwaway instance.

        Returns:
            tuple[BaseEmbedderNode, BaseEmbedConfig]: The embedder instance and its validated config.

        Raises:
            KeyError: When no embedder is registered for the given kind.
            pydantic.ValidationError: When the stored config drifted (extra="forbid" fails loudly).
        """
        # 1. Resolve the registered embedder class (bge_server, openai_compatible, …).
        node_class = cast(type[BaseEmbedderNode], NodeRegistry.get(_EMBED_FAMILY, kind))
        # 2. Re-validate the stored config (extra="forbid" — a drifted blob fails loudly).
        validated = cast(BaseEmbedConfig, node_class.Config(**config))
        # 3. A throwaway instance — only its embedding hooks are exercised (never wired in a graph).
        return node_class(id=node_id, config=validated), validated


__all__ = ["EmbedBlobResolver"]
