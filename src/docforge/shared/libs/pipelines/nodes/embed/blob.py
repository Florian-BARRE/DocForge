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
from pydantic import ValidationError

# ====== Internal Project Imports ======
import shared_libs.pipelines.nodes.embed  # noqa: F401 — ensures every embedder self-registers
from shared_libs.pipelines.build.validation_message import ValidationMessage
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import VectorLayout

# The registry family every embedder self-registers under (never string-literalled elsewhere).
_EMBED_FAMILY = "embed"


class EmbedLayoutError(ValueError):
    """A stored embed node does not build, so no store schema may be derived from it."""


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

    @classmethod
    def __layout_of(cls, node: dict[str, Any]) -> VectorLayout:
        """The layout of a found embed node (raises KeyError / ValidationError when it won't build)."""
        embedder, _ = cls.rebuild(node["kind"], dict(node.get("config") or {}))
        sparse = embedder.has_sparse()
        return VectorLayout(
            dense=embedder.has_dense(), sparse=sparse, sparse_idf=sparse and embedder.sparse_idf()
        )

    @staticmethod
    def __describe(node: dict[str, Any], exc: Exception) -> str:
        """An input-free reason a stored embed node does not build (never echoes its config/key)."""
        reason = (
            ValidationMessage.format(exc)
            if isinstance(exc, ValidationError)
            else f"unknown embed kind '{node.get('kind')}'"
        )
        return f"embed node '{node.get('id')}' (kind '{node.get('kind')}') does not build: {reason}"

    @classmethod
    def rebuild_or_raise(
        cls, node: dict[str, Any], *, node_id: str = "embedder"
    ) -> tuple[BaseEmbedderNode, BaseEmbedConfig]:
        """
        ``rebuild`` for a stored embed node, failing with an INPUT-FREE error.

        A ValidationError's text echoes the stored config (its real ``api_key`` included) and rides
        out in job errors and logged tracebacks; this raises a clean error naming the node instead.

        Args:
            node (dict): The stored embed-family node dict (``kind`` + ``config``).
            node_id (str): The id given to the throwaway instance.

        Returns:
            tuple[BaseEmbedderNode, BaseEmbedConfig]: The embedder instance and its validated config.

        Raises:
            EmbedLayoutError: The node does not build (unknown kind or drifted config).
        """
        try:
            return cls.rebuild(node["kind"], dict(node.get("config") or {}), node_id=node_id)
        except (KeyError, ValidationError) as exc:
            raise EmbedLayoutError(cls.__describe(node, exc)) from None

    @classmethod
    def layout(cls, pipeline: dict[str, Any] | None) -> VectorLayout:
        """
        The vector layout a collection's embed CONFIG dictates — DEGRADING variant for READ paths.

        Search gates, ``missing_vectors`` and the default-search correction must keep answering on
        a broken blob, so they get the default layout. Never use it to CREATE a store schema —
        ``layout_or_raise`` is the strict variant for that.

        Args:
            pipeline (dict | None): The collection's stored pipeline blob.

        Returns:
            VectorLayout: Its embedder's axes + sparse IDF flag; the legacy default (dense + sparse,
                no IDF) when the blob has no embedder or it no longer builds (logged, input-free).
        """
        node = cls.find_embed_node(pipeline or {})
        if node is None:
            return VectorLayout()
        try:
            return cls.__layout_of(node)
        except (KeyError, ValidationError) as exc:
            cls.logger.warning(f"{cls.__describe(node, exc)} — default vector layout")
            return VectorLayout()

    @classmethod
    def layout_or_raise(cls, pipeline: dict[str, Any] | None) -> VectorLayout:
        """
        The vector layout a collection's embed CONFIG dictates — STRICT variant for schema creation.

        A rebuild, an import or any store-creating path must never declare a guessed schema: a
        broken embed blob fails fast here instead of silently creating the default layout.

        Args:
            pipeline (dict | None): The collection's stored pipeline blob.

        Returns:
            VectorLayout: Its embedder's axes + sparse IDF flag (the default when it has no embedder).

        Raises:
            EmbedLayoutError: The embed node does not build (names the node, never its config).
        """
        node = cls.find_embed_node(pipeline or {})
        if node is None:
            return VectorLayout()
        try:
            return cls.__layout_of(node)
        except (KeyError, ValidationError) as exc:
            raise EmbedLayoutError(
                f"{cls.__describe(node, exc)} — the vector store schema cannot be derived; "
                "repair the collection's embed stage config"
            ) from None


__all__ = ["EmbedBlobResolver", "EmbedLayoutError"]
