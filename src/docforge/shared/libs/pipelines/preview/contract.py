# ====== Code Summary ======
# PreviewContractBuilder — builds the ingestion run-input CollectionContract from a collection row +
# its metadata-field rows, for an INLINE dry-run. It mirrors the worker's own _contract_from_rows
# exactly (same field mapping), so a preview run binds the SAME contract a real ingestion would — the
# admit node sees no difference between a dry-run and a worker run.

# ====== Third-Party Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import CollectionContract, MetadataFieldSpec


class PreviewContractBuilder:
    """Static helper: collection row + schema rows → the ingestion CollectionContract."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PreviewContractBuilder is a static-only class and cannot be instantiated.")

    @staticmethod
    def build(collection: Any, schema: list[Any]) -> CollectionContract:
        """
        Build the pipeline's run-input contract from the collection + its metadata-field rows.

        Args:
            collection (Any): The collection ORM row (id, name, supported_formats, max_file_size_bytes).
            schema (list[Any]): The collection's metadata-field rows.

        Returns:
            CollectionContract: The same contract shape the worker binds for a real ingestion run.
        """
        return CollectionContract(
            collection_id=collection.id,
            name=collection.name,
            supported_formats=list(collection.supported_formats),
            max_file_size_bytes=collection.max_file_size_bytes,
            fields=[
                MetadataFieldSpec(
                    field_name=row.field_name,
                    field_type=row.field_type,
                    required=row.required,
                    filterable=row.filterable,
                    lexical=row.lexical,
                    semantic=row.semantic,
                    origin=row.origin,
                    scope=row.scope,
                )
                for row in schema
            ],
        )


__all__ = ["PreviewContractBuilder"]
