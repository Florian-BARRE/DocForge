# ====== Code Summary ======
# FailureHandler — the three terminal paths of a run that does not succeed, each one a method:
#   * on_cooperative_cancel — an operator cancel honoured at a stage boundary: job + document
#     CANCELLED through the shared force-terminate; the caller does NOT re-raise (arq must not retry).
#   * on_hard_cancel — asyncio.CancelledError (arq's outer job_timeout, a SIGTERM, a hot-reload): the
#     terminal write is SHIELDED and driven to completion even through a second cancellation, so the
#     row is never left RUNNING forever; the caller re-raises the cancellation.
#   * on_failure — any other error: the PARTIAL execution tree (best-effort), both truths FAILED with
#     the error in clear (credential userinfo redacted) + the structured breadcrumb columns; the
#     caller re-raises so arq accounts the attempt.
# A REPLAY failure fails only the JOB: the document keeps its status and gets a warning (its previous
# chunks/points are untouched and still served).

# ====== Standard Library Imports ======
import asyncio
import uuid
from datetime import UTC, datetime

# ====== Internal Project Imports ======
from shared_libs.observability import ConfigDumpHelpers

# ====== Local Project Imports ======
from .ingest_services import IngestServices


class FailureHandler:
    """Write the terminal truths (document + job) of a cancelled or failed run."""

    def __init__(self, services: IngestServices) -> None:
        """
        Args:
            services (IngestServices): The run's services (database façade + worker logger).
        """
        self._services = services

    async def mark_document_failed(
        self, doc_uuid: uuid.UUID, replay_from: str | None, error: str
    ) -> None:
        """Flag the document after a failed run: FAILED for a full run; for a REPLAY, keep its status.

        A replay commits nothing before its single downstream save, so on failure the document's
        previous chunks/points are untouched and still served — demoting a DONE document to FAILED
        would lie. The job carries the FAILED verdict; the document only gets a warning naming the
        failed replay.
        """
        database = self._services.database
        if replay_from is None:
            await database.ingestion.mark_failed(doc_uuid)
            return
        await database.ingestion.mark_replay_failed(
            doc_uuid,
            ConfigDumpHelpers.redact_text(
                f"Replay from '{replay_from}' failed ({error}) — the previous chunks and vectors are "
                f"still served; re-run the replay or a full reingest."
            ),
        )

    async def on_cooperative_cancel(
        self, document_id: str, job_uuid: uuid.UUID, exc: Exception
    ) -> None:
        """A cooperative stop honoured at a stage boundary: mark BOTH truths CANCELLED (never FAILED).

        The caller DOES NOT re-raise — arq must not retry a job the operator explicitly cancelled.
        The shared force-terminate path also sets the document CANCELLED, so this is the single
        terminal write.
        """
        self._services.logger.info(f"Ingestion cancelled for document {document_id}: {exc}")
        await self._services.database.jobs.force_terminate(job_uuid, reason=f"cancelled: {exc}")

    async def on_hard_cancel(
        self,
        document_id: str,
        doc_uuid: uuid.UUID,
        job_uuid: uuid.UUID,
        replay_from: str | None,
    ) -> None:
        """A hard cancel (arq job_timeout, worker SIGTERM/shutdown, hot-reload): terminal-write both.

        Cancellation is a BaseException, NOT an Exception — so ``on_failure`` would MISS it and leave
        the row RUNNING forever (the "stalled" orphan). Mark BOTH truths FAILED so the job is terminal
        and the document re-ingestable; the caller then re-raises to let arq/asyncio finish the
        cancellation (best-effort: the startup reclaim + reaper are the backstops for a hard kill
        that skips this entirely).
        """
        self._services.logger.warning(f"Ingestion cancelled/timed out for document {document_id}")
        await self._commit_terminal_cancel_write(doc_uuid, job_uuid, replay_from)

    async def on_failure(
        self,
        document_id: str,
        doc_uuid: uuid.UUID,
        job_uuid: uuid.UUID,
        replay_from: str | None,
        exc: Exception,
    ) -> None:
        """Flag both truths FAILED, the error in clear; the caller re-raises so arq accounts the attempt.

        A run failure carries a structured breadcrumb (deepest failing node + fan-out item) on the
        exception; other failures (rehydrate/persist) fall back to the exception's own type.
        """
        database, logger = self._services.database, self._services.logger
        logger.exception(f"Ingestion failed for document {document_id}: {exc}")
        breadcrumb = getattr(exc, "breadcrumb", None)
        # Persist the PARTIAL per-node execution tree the runner carried out on the failure (the
        # nested tree up to AND including the failing node, each with its score/error/timing), so a
        # FAILED job's trace shows the same tree a success gets — not just the live root rows. It
        # reconciles with those rows by (job_id, node_path) exactly like the success path. Best-effort
        # BEFORE the terminal writes: a persist hiccup must NEVER mask the real job error below (it is
        # logged and swallowed). None when the failure was too early to build a tree (invalid graph,
        # preflight, rehydrate) or came from a non-runner exception — skipped cleanly, rows stand.
        partial_record = getattr(exc, "record", None)
        if partial_record is not None:
            try:
                await database.jobs.persist_execution_tree(job_uuid, partial_record)
            except Exception as persist_exc:
                logger.warning(
                    f"Persisting the partial execution tree failed for document {document_id} "
                    f"(the job is still marked failed): {persist_exc}"
                )
        await self.mark_document_failed(doc_uuid, replay_from, f"{type(exc).__name__}: {exc}")
        # Redact any URL userinfo (credentials before the host) a provider exception may echo (a
        # credential-bearing base_url surfaced in a transport/auth error) before it is persisted on
        # the job row — the message is otherwise preserved verbatim for diagnostics.
        await database.jobs.mark_failed(
            job_uuid,
            error=ConfigDumpHelpers.redact_text(f"{type(exc).__name__}: {exc}"),
            finished_at=datetime.now(UTC),
            failed_node_id=breadcrumb.node_id if breadcrumb else None,
            failed_node_kind=breadcrumb.node_kind if breadcrumb else None,
            failed_item_index=breadcrumb.item_index if breadcrumb else None,
            error_type=breadcrumb.error_type if breadcrumb else type(exc).__name__,
        )

    async def _commit_terminal_cancel_write(
        self, doc_uuid: uuid.UUID, job_uuid: uuid.UUID, replay_from: str | None
    ) -> None:
        """Commit BOTH terminal truths (document + job FAILED) for a hard-cancelled run, guaranteed.

        A hard cancel tears the task down with ``asyncio.CancelledError``. The terminal write must
        still commit so the job is terminal and the document re-ingestable — otherwise the row is
        left RUNNING forever (a stalled orphan). Two hazards are handled here:

        1. A SECOND cancellation racing the write. ``asyncio.shield`` stops the FIRST cancellation
           from killing the write, but a second cancellation raised while awaiting the shield
           abandons the await — the shielded task keeps running unobserved, so a naive
           ``await asyncio.shield(...)`` can skip the write entirely. The write is therefore driven
           to completion here: repeated cancellations of OUR wait are absorbed and the same shielded
           task is re-awaited until it is truly done.
        2. ``CancelledError`` is a BaseException, so a bare ``except Exception`` would MISS it. It is
           handled explicitly (the ``except asyncio.CancelledError`` inside the loop).

        Best-effort by contract: the startup reclaim + reaper are the backstops for a hard kill that
        skips this path entirely, so a genuine write error is logged, never raised.

        Args:
            doc_uuid (uuid.UUID): The document to mark FAILED (re-ingestable).
            job_uuid (uuid.UUID): The job to mark FAILED (terminal).
            replay_from (str | None): Set for a replay job — the document then keeps its status (its
                previous content is untouched) and only gets a warning.
        """
        database = self._services.database

        async def _writes() -> None:
            # 1. Both truths in one shielded unit so a second cancel cannot land BETWEEN them (which
            #    is exactly how the old two-await form left the JOB row non-terminal).
            await self.mark_document_failed(doc_uuid, replay_from, "cancelled or timed out")
            await database.jobs.mark_failed(
                job_uuid,
                error="cancelled or timed out (worker shutdown / job timeout) — re-ingest to retry",
                finished_at=datetime.now(UTC),
                error_type="CancelledError",
            )

        # 2. Drive the shielded write to completion, absorbing repeated cancellations of our own wait.
        task = asyncio.ensure_future(_writes())
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                # OUR wait was cancelled again (a second cancel); the shielded write keeps running —
                # re-await it. Only stop if the task itself was somehow cancelled (it is shielded, so
                # this cannot happen in practice, but the guard keeps the loop honest).
                if task.cancelled():  # pragma: no cover - the write is shielded, never cancelled
                    return
                continue
            except Exception:
                # The write itself raised; the task is now done — fall through to report it below.
                break

        # 3. Report a genuine write failure (best-effort). A cancellation of the write itself cannot
        #    happen (it is shielded), so ``task.exception()`` is safe to read once done.
        if not task.cancelled() and task.exception() is not None:  # pragma: no cover - best-effort
            self._services.logger.warning(
                f"Terminal write during cancel failed (backstops cover it): {task.exception()}"
            )


__all__ = ["FailureHandler"]
