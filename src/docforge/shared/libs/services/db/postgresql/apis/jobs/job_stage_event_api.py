# ====== Code Summary ======
# JobStageEventApi — The per-stage event timeline of a job: append and finalize a stage row,
# materialize the full execution tree, and read the trace back as a stable pre-order walk (or one
# row by id).

# ====== Standard Library Imports ======
import re
import uuid
from datetime import datetime
from decimal import Decimal

# ====== Third-Party Library Imports ======
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.public_models import TextSanitizer

from ...tables import (
    JobStageEvent,
)

# ====== Local Project Imports ======
from ..execution_tree import ExecutionTreeFlattener, TraceRefs


class JobStageEventApi:
    """Static data-access API: the per-stage event timeline and the persisted execution tree."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobStageEventApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def record_event(session: AsyncSession, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline and return it (flushed, id assigned)."""
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def finalize_event(
        session: AsyncSession,
        event_id: uuid.UUID,
        status: str,
        finished_at: datetime,
        detail: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        cost_usd: Decimal | None,
    ) -> None:
        """
        Close an OPEN stage-event row (opened at the stage's START) with its outcome.

        The stage timeline now writes a "running" row on START and finalizes it here on END, so a
        run cut before END leaves the row visibly open (later closed as failed by ``mark_failed``).

        Args:
            session (AsyncSession): The active DB session.
            event_id (uuid.UUID): The open row's id.
            status (str): Final status (success / skipped / failed).
            finished_at (datetime): When the stage ended.
            detail (str | None): Duration or error detail.
            prompt_tokens (int | None): Paid input tokens for the stage (None if no paid call).
            completion_tokens (int | None): Paid output tokens for the stage.
            cost_usd (Decimal | None): USD cost (None when unpriced).
        """
        await session.execute(
            update(JobStageEvent)
            .where(JobStageEvent.id == event_id)
            .values(
                status=status,
                finished_at=finished_at,
                detail=detail,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
            )
        )

    @staticmethod
    async def persist_execution_tree(
        session: AsyncSession,
        job_id: uuid.UUID,
        record: NodeExecutionRecord,
        refs: dict[str, TraceRefs] | None = None,
    ) -> None:
        """
        Persist the FULL per-node execution tree onto the job's stage timeline (materialized path).

        Walks the run's outermost record into flat materialized-path rows (every node — nested group
        children and per-item ForEach body instances included) and reconciles them with the stage
        timeline by ``(job_id, node_path)``:

        - A node whose path already has a row — the live ROOT rows the ``JobProgressRecorder`` opened
          at each stage START (now stamped with ``node_path = node_id``), or a row from a previous
          persist — is UPDATED in place with its tree coordinates + score + trace capture (shape
          summaries always, full-payload refs when present). Its status/timing and the subtree-
          aggregated token/cost meter the recorder wrote are left untouched.
        - A node with no row yet — every NESTED node, which the live recorder only counted — is
          INSERTED with its own status/kind/duration/error/usage/score, tree coordinates and trace.

        The trace capture is advisory: ``input_summary``/``output_summary`` (the cheap shape tier) are
        written inline from the record whenever they were captured; ``input_ref``/``output_ref`` +
        ``has_full_*`` are written from ``refs`` for the full tier (the worker stored the payloads in
        the object store BEFORE this call). A node absent from ``refs`` simply keeps ``has_full`` false.

        Idempotent: a second call finds every path already present and simply re-updates it, so the
        empty-chunk warning path and a normal success path can both call it without duplicating rows.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job whose trace is being materialized.
            record (NodeExecutionRecord): The run's outermost execution record (the pipeline group).
            refs (dict[str, TraceRefs] | None): Per-node-path object-store references to the full
                input/output payloads (full trace tier only); None at the shape/off tiers.
        """
        # 1. Flatten the tree into parent-before-child materialized-path rows.
        flat = ExecutionTreeFlattener.flatten(record)
        if not flat:
            return
        refs = refs or {}

        # 2. The paths already on the timeline (the live root rows + any prior persist), so each node
        #    is reconciled to at most one row — never duplicated.
        existing = await session.execute(
            select(JobStageEvent.node_path, JobStageEvent.id).where(
                JobStageEvent.job_id == job_id, JobStageEvent.node_path.is_not(None)
            )
        )
        row_id_by_path = {path: row_id for path, row_id in existing.all()}

        # 3. Reconcile each node: fill tree coordinates + score + trace on an existing row, insert the
        #    rest. The trace refs (full tier) come from the pre-stored object-store keys; the shape
        #    summaries ride on the record itself. ``has_full_*`` is derived from whether a ref exists.
        for node in flat:
            rec = node.record
            score = rec.score
            node_refs = refs.get(node.node_path, TraceRefs())
            existing_id = row_id_by_path.get(node.node_path)
            if existing_id is not None:
                await session.execute(
                    update(JobStageEvent)
                    .where(JobStageEvent.id == existing_id)
                    .values(
                        depth=node.depth,
                        parent_path=node.parent_path,
                        item_index=node.item_index,
                        score=score,
                        input_summary=rec.input_summary,
                        output_summary=rec.output_summary,
                        input_ref=node_refs.input_ref,
                        output_ref=node_refs.output_ref,
                        has_full_input=node_refs.input_ref is not None,
                        has_full_output=node_refs.output_ref is not None,
                    )
                )
                continue
            # A nested node the recorder never opened a row for: insert it whole. Duration/error go
            # into ``detail`` (the record carries a relative duration, not absolute timestamps, so
            # started_at/finished_at stay NULL — this keeps nested rows out of the timestamp-gated
            # avg_stage_durations read). Raw token counts are reported when present; per-leaf USD
            # pricing stays at the aggregating root row, so cost_usd is left NULL here.
            usage = rec.usage
            # NUL guard: a nested node's error message can echo raw document bytes (incl. U+0000) —
            # strip it so persisting the trace of a FAILED run never itself raises on the text column.
            detail = TextSanitizer.strip_nul(
                f"{rec.error.error_type}: {rec.error.message}"
                if rec.error is not None
                else f"{rec.duration_ms:.0f} ms"
            )
            session.add(
                JobStageEvent(
                    job_id=job_id,
                    stage=rec.node_id[:64],
                    status=rec.status.value,
                    node_kind=rec.kind,
                    detail=detail,
                    prompt_tokens=usage.prompt_tokens if usage is not None else None,
                    completion_tokens=usage.completion_tokens if usage is not None else None,
                    node_path=node.node_path,
                    depth=node.depth,
                    parent_path=node.parent_path,
                    item_index=node.item_index,
                    score=score,
                    input_summary=rec.input_summary,
                    output_summary=rec.output_summary,
                    input_ref=node_refs.input_ref,
                    output_ref=node_refs.output_ref,
                    has_full_input=node_refs.input_ref is not None,
                    has_full_output=node_refs.output_ref is not None,
                )
            )
        await session.flush()

    @staticmethod
    def _trace_sort_key(event: JobStageEvent) -> tuple:  # type: ignore[type-arg]
        """
        Natural-order sort key for a stage-event row, giving a stable pre-order tree walk.

        Ordering by the materialized ``node_path`` yields a pre-order DFS (a parent's path is a
        lexical prefix of every descendant's, so the parent leads its subtree). Each maximal digit
        run compares NUMERICALLY so ForEach body items sort by ascending index (``[2]`` before
        ``[10]`` — a plain string sort inverts them). Legacy rows (``node_path`` NULL, written before
        the tree columns landed) have no path, so they fall back to insertion order (``created_at``)
        and lead the list.

        Args:
            event (JobStageEvent): One stage-event row.

        Returns:
            tuple: A comparable key — ``(0, created_at)`` for legacy rows, ``(1, natural-tokens)`` for
                path-carrying rows (the leading discriminator keeps the two groups from cross-typing).
        """
        if event.node_path is None:
            return (0, event.created_at)
        tokens = tuple(
            int(chunk) if chunk.isdigit() else chunk
            for chunk in re.split(r"(\d+)", event.node_path)
            if chunk != ""
        )
        return (1, tokens)

    @staticmethod
    def events_query(  # type: ignore[no-untyped-def]
        job_id: uuid.UUID,
        include_summaries: bool = True,
        after_created_at: datetime | None = None,
    ):
        """Build the stage-event SELECT for a job, optionally LEAN (summaries deferred) and/or INCREMENTAL.

        The flat timeline (stage/status/kind/path/timings/tokens/cost/score) is cheap; the two JSONB
        shape summaries (``input_summary``/``output_summary``) are the only wide, TOAST-able columns.
        The high-frequency poll path (the live SSE stream's per-tick delta) never renders them, so it
        passes ``include_summaries=False`` to ``defer`` both columns OUT of the SELECT — Postgres then
        never reads or de-TOASTs them. The one-shot trace read keeps them (default True).

        ``after_created_at`` makes the read INCREMENTAL: the SSE stream passes its delta cursor (the
        newest ``created_at`` it has already emitted) so each poll fetches ONLY the rows inserted
        since — never re-reading the whole timeline every tick. ``created_at`` is the natural insertion
        ordinal (live stage rows land in their own per-stage transactions; the post-run execution-tree
        rows land together in one, all newer than every live row), so ``> cursor`` cleanly yields the
        new rows. None (the default) keeps the full read — a fresh stream open replays everything.
        Exposed as a builder so a unit test can assert the rendered column/predicate set without a DB.

        Args:
            job_id (uuid.UUID): The job whose stage-event rows to select.
            include_summaries (bool): Keep the JSONB summary columns (True, the full trace read) or
                defer them out of the SELECT (False, the lean poll path).
            after_created_at (datetime | None): When set, only rows with a strictly greater
                ``created_at`` (the incremental delta); None reads the whole timeline.

        Returns:
            Select: The composed statement.
        """
        stmt = select(JobStageEvent).where(JobStageEvent.job_id == job_id)
        if after_created_at is not None:
            stmt = stmt.where(JobStageEvent.created_at > after_created_at)
        if not include_summaries:
            stmt = stmt.options(
                defer(JobStageEvent.input_summary), defer(JobStageEvent.output_summary)
            )
        return stmt

    @classmethod
    async def list_events(
        cls,
        session: AsyncSession,
        job_id: uuid.UUID,
        include_summaries: bool = True,
        after_created_at: datetime | None = None,
    ) -> list[JobStageEvent]:
        """Return a job's per-node trace as a stable pre-order tree walk (parent before children).

        The full tree is materialized on the rows (``node_path``/``depth``/``parent_path``/
        ``item_index``), so this sorts by a natural key on ``node_path`` (see ``_trace_sort_key``):
        a parent precedes its children and ForEach body items sort by ascending index. Legacy rows
        with no path lead the list in insertion order. Sorting in Python keeps the numeric ForEach
        order a SQL string ``ORDER BY`` cannot express; the per-job row count is small.

        ``include_summaries=False`` DEFERS the wide JSONB shape summaries out of the SELECT for the
        high-frequency poll path (the live SSE stream). The deferred attributes MUST NOT be read off
        the returned rows (an async lazy-load would fail) — the caller pairs this with
        ``JobEvent.from_row(..., include_summaries=False)`` so the summaries are reported None.

        ``after_created_at`` is the SSE stream's delta cursor: when set, only rows inserted since are
        read (the returned batch is still tree-sorted, so ordering is identical to a full read of that
        same set). None reads the whole timeline (the one-shot trace read and a fresh stream open).
        """
        result = await session.execute(
            cls.events_query(job_id, include_summaries, after_created_at)
        )
        return sorted(result.scalars().all(), key=cls._trace_sort_key)

    @staticmethod
    async def get_event(
        session: AsyncSession, job_id: uuid.UUID, event_id: uuid.UUID
    ) -> JobStageEvent | None:
        """
        Fetch ONE stage-event row addressed by (job_id, event_id), or None.

        The full-payload fetch route addresses a single trace node by its row id; the ``job_id`` is
        AND-ed into the predicate (not merely trusted from the path) so an event id can never be read
        under the wrong job — the collection-scope gate is enforced on the job, so binding the row to
        that job closes any cross-job id-guessing.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job the row must belong to.
            event_id (uuid.UUID): The stage-event row's id.

        Returns:
            JobStageEvent | None: The row, or None when no row has that id under that job.
        """
        result = await session.execute(
            select(JobStageEvent).where(
                JobStageEvent.id == event_id, JobStageEvent.job_id == job_id
            )
        )
        return result.scalars().first()


__all__ = ["JobStageEventApi"]
