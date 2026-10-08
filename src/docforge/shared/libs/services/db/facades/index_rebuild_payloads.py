# ====== Code Summary ======
# The typed errors and result payloads of the rebuild_index job: the admission conflicts the API maps
# to 409, the worker-side abort/refusal errors, the Qdrant copy summary, and the post-swap
# reconciliation outcome.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# The rebuild's own-row probe: True once its job is terminal or a cooperative cancel was requested.
AbortProbe = Callable[[], Awaitable[bool]]


class IndexRebuildActiveError(Exception):
    """A rebuild_index job is live on the collection — ingest admissions and a 2nd rebuild refuse."""

    def __init__(self, collection_id: uuid.UUID, job_id: uuid.UUID | None) -> None:
        """
        Args:
            collection_id (uuid.UUID): The collection being rebuilt.
            job_id (uuid.UUID | None): The live rebuild job (None when only the index backstop knew).
        """
        super().__init__(f"Collection {collection_id} has an active index rebuild ({job_id}).")
        self.collection_id = collection_id
        self.job_id = job_id


class CollectionBusyError(Exception):
    """Other jobs are live on the collection — a rebuild is refused until they finish."""

    def __init__(self, collection_id: uuid.UUID, job_ids: list[uuid.UUID]) -> None:
        """
        Args:
            collection_id (uuid.UUID): The collection whose rebuild was refused.
            job_ids (list[uuid.UUID]): The live jobs blocking it.
        """
        super().__init__(f"Collection {collection_id} has {len(job_ids)} active job(s).")
        self.collection_id = collection_id
        self.job_ids = job_ids


class RebuildUnsupportedError(Exception):
    """The collection has chunk-scope LEXICAL fields — a rebuild would destroy their vectors."""

    def __init__(self, collection_id: uuid.UUID, fields: list[str]) -> None:
        """
        Args:
            collection_id (uuid.UUID): The collection whose rebuild was refused.
            fields (list[str]): The chunk-scope lexical fields (legacy — new ones are rejected at 422).
        """
        super().__init__(f"Collection {collection_id} has chunk-scope lexical fields {fields}.")
        self.collection_id = collection_id
        self.fields = fields


class RebuildCancelledError(Exception):
    """The rebuild's job row went terminal or asked to stop — aborted BEFORE the swap."""


@dataclass(slots=True)
class StoreCopyResult:
    """
    What the Qdrant phase of a rebuild did.

    Attributes:
        physical (str | None): The new physical collection the stable name now resolves to (None when
            the collection had no Qdrant space — nothing to rebuild).
        copied_points (int): Points copied into the new store.
        first_rebuild (bool): True when the stable name was a physical collection (non-atomic swap).
        document_ids (set[str]): The ``document_id`` payloads seen while copying.
        carried_vectors (set[str]): Every vector name at least one copied point carried.
        reencoded_sparse_points (int): Points whose content sparse vector was re-encoded from the
            chunk text (the old one came from another sparse provider, or was absent).
        sparse_reencoded (bool): The copy re-encoded the content sparse vector through the
            configured sparse provider instead of copying it (its space is now the current one).
    """

    physical: str | None
    copied_points: int = 0
    first_rebuild: bool = False
    document_ids: set[str] = field(default_factory=set)
    carried_vectors: set[str] = field(default_factory=set)
    reencoded_sparse_points: int = 0
    sparse_reencoded: bool = False


@dataclass(slots=True)
class RebuildReconcileResult:
    """
    What the post-swap reconciliation did.

    Attributes:
        missing_vectors (list[str]): Named vectors the schema still needs but the store lacks.
        needs_reindex (bool): The collection's flag after the rebuild.
        removed_documents (int): Documents deleted in Postgres during the copy whose points were purged.
        overrides_applied (int): Chunk enabled overrides re-applied onto the new store.
        reingest_required_fields (list[str]): Chunk-scope semantic fields whose vector no point
            carries — a rebuild cannot fill them (content is copied, the backfill is document-scope).
        dense_space_changed (bool): The dense embed provider/model changed since the last ingest —
            a rebuild copies the dense vectors and cannot re-embed them, so ``needs_reindex`` stays
            raised until a reingest.
    """

    missing_vectors: list[str] = field(default_factory=list)
    reingest_required_fields: list[str] = field(default_factory=list)
    needs_reindex: bool = False
    removed_documents: int = 0
    overrides_applied: int = 0
    dense_space_changed: bool = False


__all__ = [
    "AbortProbe",
    "IndexRebuildActiveError",
    "RebuildUnsupportedError",
    "RebuildCancelledError",
    "CollectionBusyError",
    "StoreCopyResult",
    "RebuildReconcileResult",
]
