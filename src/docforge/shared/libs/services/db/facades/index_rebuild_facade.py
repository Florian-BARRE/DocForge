# ====== Code Summary ======
# IndexRebuildFacade — the Postgres side of the rebuild_index job, exposed as ONE façade
# (``Database.index_rebuild``) over two cohesive collaborators: IndexRebuildAdmission (collection row
# FOR UPDATE admission + the worker's bounded wait for live jobs) and IndexRebuildReconciler (post-swap
# override/orphan reconciliation + the honest needs_reindex derivation).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.tables import Job
from shared_libs.services.db.qdrant import QdrantClient

# ====== Local Project Imports ======
from .index_rebuild_admission import IndexRebuildAdmission
from .index_rebuild_payloads import AbortProbe, RebuildReconcileResult, StoreCopyResult
from .index_rebuild_reconciler import IndexRebuildReconciler
from .index_state_facade import IndexStateFacade


class IndexRebuildFacade(LoggerClass):
    """Admission, wait and post-swap reconciliation of a collection's index rebuild."""

    def __init__(
        self, postgres: PostgresClient, qdrant: QdrantClient, index_state: IndexStateFacade
    ) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (jobs, overrides, baseline).
            qdrant (QdrantClient): The vector store (override + orphan reconciliation writes).
            index_state (IndexStateFacade): The declared-vs-needed view (post-swap re-check).
        """
        LoggerClass.__init__(self)
        self._admission = IndexRebuildAdmission(postgres)
        self._reconciler = IndexRebuildReconciler(postgres, qdrant, index_state)

    async def active_rebuild(self, collection_id: uuid.UUID) -> Job | None:
        """Return the collection's live rebuild job (unlocked read — the API's fast pre-check)."""
        return await self._admission.active_rebuild(collection_id)

    async def admit(self, collection_id: uuid.UUID) -> uuid.UUID:
        """
        Mint a PENDING rebuild_index job, serialised on the collection row.

        Raises:
            IndexRebuildActiveError: A rebuild is already pending/running.
            RebuildUnsupportedError: The schema has (legacy) chunk-scope lexical fields.
            CollectionBusyError: Other jobs are live on the collection.
            LookupError: The collection does not exist.

        Returns:
            uuid.UUID: The new job id.
        """
        return await self._admission.admit(collection_id)

    async def wait_for_idle(
        self,
        collection_id: uuid.UUID,
        job_id: uuid.UUID,
        timeout_s: float,
        poll_s: float = 2.0,
        should_abort: AbortProbe | None = None,
    ) -> None:
        """
        Wait until no OTHER job is live on the collection (bounded).

        Raises:
            TimeoutError: Jobs are still live after ``timeout_s`` (nothing was touched yet).
            RebuildCancelledError: The rebuild's own row asked to stop while waiting.
        """
        await self._admission.wait_for_idle(
            collection_id, job_id, timeout_s, poll_s=poll_s, should_abort=should_abort
        )

    async def reconcile(
        self, collection_id: uuid.UUID, copy: StoreCopyResult
    ) -> RebuildReconcileResult:
        """
        Converge the new store with Postgres after the swap, then derive ``needs_reindex``.

        Args:
            collection_id (uuid.UUID): The rebuilt collection.
            copy (StoreCopyResult): The copy summary (documents seen, vectors carried).

        Returns:
            RebuildReconcileResult: Overrides applied, documents purged, missing vectors, flag.
        """
        return await self._reconciler.reconcile(collection_id, copy)


__all__ = ["IndexRebuildFacade"]
