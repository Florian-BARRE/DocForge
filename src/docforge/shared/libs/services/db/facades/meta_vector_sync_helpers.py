# ====== Code Summary ======
# MetaVectorSyncHelpers — the pure, I/O-free conventions the MetaVectorSyncFacade leans on: locate a
# collection's own embed node inside its serialised ingestion blob, rebuild that embedder from the
# registry (class + extra="forbid" config, so a drifted blob fails loudly — the same rebuild the
# search encode node does), render a document-scope metadata value to the short text that gets
# embedded (a list joins with ", ", a scalar stringifies, empty renders to None), and PLAN which
# named vector each searchable field feeds (declared-guarded) so the facade can embed a whole axis
# in ONE batched pass. No store access here; the facade drives the embedder's hooks and writes Qdrant.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.services.db.qdrant import VectorNames


class MetaVectorSyncHelpers:
    """Static, I/O-free helpers for rebuilding a collection's embedder and rendering meta values."""

    logger = loggerplusplus.bind(identifier="MetaVectorSyncHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetaVectorSyncHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def __bucket_axis(
        cls,
        vector_name: str,
        text: str,
        declared: set[str],
        bucket: list[tuple[str, str]],
        axis_label: str,
    ) -> None:
        """Append ``(vector_name, text)`` to its axis bucket, or warn when the vector is undeclared.

        A collection can only carry a named vector it declared at creation, so a semantic/lexical
        field pointing at an undeclared vector is skipped loudly rather than written (and rejected).
        """
        if vector_name in declared:
            bucket.append((vector_name, text))
        else:
            cls.logger.warning(
                f"{axis_label} meta vector '{vector_name}' not declared on collection — skipped"
            )

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

    @classmethod
    def plan_meta_axes(
        cls,
        rows: list[tuple[str, Any, bool, bool]],
        declared_dense: set[str],
        declared_sparse: set[str],
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """
        Bucket each field's rendered value into the named vectors it feeds — dense and/or sparse.

        Mirrors the per-field routing the facade needs, but as a PURE plan so the facade can embed
        each axis in a SINGLE batched pass instead of one forward pass per field. An empty value
        carries no vector; a semantic/lexical field whose named vector the collection never declared
        is skipped with a warning. A both-axes field simply appears in both buckets.

        Args:
            rows (list[tuple[str, Any, bool, bool]]): (field name, value, semantic, lexical) rows.
            declared_dense (set[str]): The dense named vectors the collection actually declares.
            declared_sparse (set[str]): The sparse named vectors the collection actually declares.

        Returns:
            tuple[list[tuple[str, str]], list[tuple[str, str]]]: The dense and the sparse
                ``(vector_name, text)`` pairs, each ready for one batched embed call.
        """
        dense_fields: list[tuple[str, str]] = []
        sparse_fields: list[tuple[str, str]] = []
        for field_name, value, semantic, lexical in rows:
            # 1. Empty values carry no vector (mirrors the embed node's skip).
            text = cls.render_value(value)
            if text is None:
                continue
            # 2. Semantic → the dense meta vector; lexical → the sparse one (each declared-guarded).
            if semantic:
                cls.__bucket_axis(
                    VectorNames.field_dense(field_name), text, declared_dense, dense_fields, "Dense"
                )
            if lexical:
                cls.__bucket_axis(
                    VectorNames.field_sparse(field_name),
                    text,
                    declared_sparse,
                    sparse_fields,
                    "Sparse",
                )
        return dense_fields, sparse_fields

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
