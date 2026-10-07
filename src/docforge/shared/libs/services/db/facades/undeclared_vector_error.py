# ====== Code Summary ======
# UndeclaredVectorError — raised when an ingest's points carry a named vector the collection's Qdrant
# store never declared. Qdrant cannot add a named vector to a live collection, so such an upsert would
# fail with an opaque 400 "Not existing vector name" on EVERY ingest. The message names the field(s)
# and the one action that fixes it (an index rebuild); the class name is the job's error_type.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Mapping, Sequence


class UndeclaredVectorError(ValueError):
    """An ingest point carries a named vector the collection's Qdrant store does not declare."""

    @classmethod
    def for_vectors(
        cls,
        collection_id: uuid.UUID,
        vectors: Sequence[str],
        field_of: Mapping[str, str],
    ) -> "UndeclaredVectorError":
        """
        Build the error naming each offending field (or the raw vector name when no field maps).

        Args:
            collection_id (uuid.UUID): The collection whose store lacks the vectors.
            vectors (Sequence[str]): The undeclared vector names, sorted.
            field_of (Mapping[str, str]): Vector name → the metadata field that feeds it.

        Returns:
            UndeclaredVectorError: The error with the rebuild instruction.
        """
        # 1. Name the schema field when the vector is a field's, else the vector itself.
        labels = ", ".join(
            f"field '{field_of[vector]}'" if vector in field_of else f"vector '{vector}'"
            for vector in vectors
        )
        return cls(
            f"{labels} has no indexed vector in this collection — run rebuild_index "
            f"(POST /api/v1/collections/{collection_id}/rebuild-index)"
        )


__all__ = ["UndeclaredVectorError"]
