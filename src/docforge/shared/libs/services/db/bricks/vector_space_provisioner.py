# ====== Code Summary ======
# VectorSpaceProvisioner — the one "ensure the Qdrant vector space from the metadata schema and the
# embedder layout" block: the semantic / lexical / filterable field projections of the schema are
# derived here, once, and handed to ``QdrantCollectionApi.ensure`` (create on first use, otherwise
# reconcile additively). Shared by the ingestion indexer, the bundle importer (transfer) and the
# store rebuild; each caller still owns where the schema, the layout and the dense size come from.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import QdrantCollectionApi


class VectorSpaceProvisioner:
    """Static provisioner of a Qdrant vector space from the metadata schema + the embed layout."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("VectorSpaceProvisioner is a static-only class and cannot be instantiated.")

    @staticmethod
    async def ensure(
        client: AsyncQdrantClient,
        name: str,
        schema: Sequence[MetadataField],
        dense_dim: int,
        layout: VectorLayout | None,
    ) -> set[str]:
        """
        Ensure the Qdrant collection ``name`` exists with the vector space the schema + layout dictate.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection to create or reconcile (a stable or a physical name).
            schema (Sequence[MetadataField]): The collection's metadata schema (slugs already validated).
            dense_dim (int): Dense vector dimension (0 when the layout has no dense vector).
            layout (VectorLayout | None): The embedder's config-derived layout (None = the legacy
                dense + sparse, no-IDF layout).

        Returns:
            set[str]: The fields whose named vector is missing or mismatched on an existing store
                (reindex-required); empty for a fresh one.
        """
        # 1. Imported here: ``facades`` imports this package, and its ``helpers`` module (the single
        #    FieldType -> payload-index mapping) would otherwise close an import cycle at load time.
        from shared_libs.services.db.facades.helpers import DatabaseHelpers

        # 2. Project the schema onto the three field families Qdrant needs, then ensure the store.
        return await QdrantCollectionApi.ensure(
            client,
            name,
            dense_dim=dense_dim,
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
            layout=layout,
        )


__all__ = ["VectorSpaceProvisioner"]
