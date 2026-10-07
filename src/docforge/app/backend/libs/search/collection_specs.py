# ====== Code Summary ======
# SearchCollectionSpecs — pure lookups of the collection facts the search routes need: the embed
# node in the stored pipeline blob (via the shared EmbedBlobResolver) and the display-title field row.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.public_models import FieldScope
from shared_libs.services.db.postgresql.tables import MetadataField


class SearchCollectionSpecs:
    """Static, store-free lookups over a collection's blob and schema."""

    logger = loggerplusplus.bind(identifier="SearchCollectionSpecs")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchCollectionSpecs is a static-only class and cannot be instantiated.")

    @staticmethod
    def embed_node_blob(pipeline: dict[str, Any]) -> ActionNodeBlob | None:
        """
        Find the collection's embed node in its serialised pipeline blob.

        Args:
            pipeline (dict): The stored pipeline blob (a serialised group topology).

        Returns:
            ActionNodeBlob | None: The embed action node, or None when the pipeline has none.
        """
        # 1. Delegate the (possibly nested) walk to the shared resolver; the embed family is
        #    single-use, so it returns THE one. None when the pipeline carries no embedder.
        node = EmbedBlobResolver.find_embed_node(pipeline)
        return ActionNodeBlob(**node) if node is not None else None

    @staticmethod
    def title_field_spec(collection: Any, schema: Sequence[MetadataField]) -> MetadataField | None:
        """
        Resolve the collection's ``title_field`` name to its DOCUMENT-scope schema row.

        ``title_field`` is a soft reference (no FK): a name that no longer resolves to a
        document-scope field (renamed/deleted/chunk-scope) yields None, so hits fall back to the
        parser title instead of failing.

        Args:
            collection (Any): The collection row (its ``title_field`` may be absent or None).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            MetadataField | None: The display-title field row, or None when unset/unresolvable.
        """
        # 1. Unset → parser titles.
        name = getattr(collection, "title_field", None)
        if not name:
            return None
        # 2. Only a document-scope field can title a document.
        return next(
            (
                row
                for row in schema
                if row.field_name == name
                and getattr(row, "scope", FieldScope.DOCUMENT) == FieldScope.DOCUMENT
            ),
            None,
        )


__all__ = ["SearchCollectionSpecs"]
