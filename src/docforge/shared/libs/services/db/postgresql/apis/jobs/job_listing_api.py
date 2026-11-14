# ====== Code Summary ======
# JobListingApi — Jobs joined to their display names and the triage list: the shared filter /
# ordering predicates, the per-collection and fleet-wide paged lists, and the matching count.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import DisplayTitleResolver, FieldScope

from ...tables import (
    Collection,
    Document,
    DocumentMetadata,
    Job,
    JobStatus,
    MetadataField,
)

# ====== Local Project Imports ======
from .job_api_models import JobWithNames


class JobListingApi:
    """Static data-access API: jobs joined to display names, the triage list and its count."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobListingApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def _job_filters(  # type: ignore[no-untyped-def]
        collection_id: uuid.UUID | None,
        statuses: Sequence[JobStatus] | None,
        *,
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ):
        """
        Build the WHERE conditions shared by the fleet-wide list + count reads — the triage filter set.

        Every condition is additive and optional, so an omitted argument widens the scan: no
        ``collection_id`` is fleet-wide, no ``statuses`` is every status, and the remaining filters
        (stage / error class / id search / created-date range) simply narrow the match when present.
        Keeping the predicate in one place is what keeps the list and its total counting the same rows.

        Args:
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.
            statuses (Sequence[JobStatus] | None): Restrict to these statuses, or None/empty for all.
            stage (str | None): Restrict to jobs whose ``current_stage`` equals this (the node the job
                is in / died in).
            error_type (str | None): Restrict to jobs whose structured failure class equals this.
            search (str | None): Case-insensitive PREFIX match on the job id OR document id (cast to
                text) — supports pasting a full id or a leading fragment from a triage search box.
            created_after (datetime | None): Keep jobs created at or after this instant (range start).
            created_before (datetime | None): Keep jobs created at or before this instant (range end).

        Returns:
            list: The SQLAlchemy conditions (possibly empty — an unfiltered, fleet-wide scan).
        """
        conditions = []
        if collection_id is not None:
            conditions.append(Job.collection_id == collection_id)
        if statuses:
            conditions.append(Job.status.in_(list(statuses)))
        if stage:
            conditions.append(Job.current_stage == stage)
        if error_type:
            conditions.append(Job.error_type == error_type)
        if created_after is not None:
            conditions.append(Job.created_at >= created_after)
        if created_before is not None:
            conditions.append(Job.created_at <= created_before)
        if search:
            # Prefix match on either id cast to text: a full id is an exact prefix, a fragment a
            # leading match. No btree can serve a LIKE on a cast, but the job table is small and the
            # match is always paired with LIMIT — acceptable for the triage search box (see handoff).
            pattern = f"{search}%"
            conditions.append(
                or_(
                    cast(Job.id, String).ilike(pattern),
                    cast(Job.document_id, String).ilike(pattern),
                )
            )
        return conditions

    @staticmethod
    def _with_names_select():  # type: ignore[no-untyped-def]
        """The base ``job`` select LEFT-joined to its document/collection display names.

        Outer joins so a job whose document or collection was deleted mid-flight still returns (with a
        None name) rather than vanishing from the monitoring view. The collection's ``title_field``
        and that field's stored value for the job's document ride along as two more columns (a
        correlated scalar subquery seeking the unique ``(collection_id, field_name)`` +
        ``(document_id, field_id)`` indexes), so a page of jobs resolves every display title in the
        SAME single statement — no per-row read. A NULL ``title_field`` matches nothing → NULL value.
        """
        title_value = (
            select(DocumentMetadata.value)
            .join(MetadataField, MetadataField.id == DocumentMetadata.field_id)
            .where(
                DocumentMetadata.document_id == Job.document_id,
                MetadataField.collection_id == Job.collection_id,
                MetadataField.field_name == Collection.title_field,
                MetadataField.scope == FieldScope.DOCUMENT,
            )
            .correlate(Job, Collection)
            .scalar_subquery()
        )
        return (
            select(
                Job,
                Document.filename,
                Document.title,
                Collection.name,
                Collection.title_field,
                title_value,
            )
            .outerjoin(Document, Document.id == Job.document_id)
            .outerjoin(Collection, Collection.id == Job.collection_id)
        )

    @staticmethod
    def _row_to_names(row: Sequence) -> JobWithNames:  # type: ignore[type-arg]
        """
        Build a JobWithNames from one ``_with_names_select`` row.

        The parsed title column defaults to "" pre-parse; it is surfaced as None so the UI can cleanly
        fall back to the filename instead of rendering a blank string. The display title applies the
        shared DisplayTitleResolver rule to the joined ``title_field`` value (same rule as the
        document list/grid/detail), so a job row names its document exactly like the corpus does.
        """
        job, filename, title, collection_name, title_field, title_value = row
        parsed = title or None
        display = DisplayTitleResolver.resolve(parsed, {title_field: title_value}, title_field)
        return JobWithNames(
            job=job,
            document_filename=filename,
            document_title=parsed,
            collection_name=collection_name,
            document_display_title=display or None,
        )

    @classmethod
    async def get_with_names(cls, session: AsyncSession, job_id: uuid.UUID) -> JobWithNames | None:
        """Fetch one job joined to its document filename + title + collection name, or None."""
        result = await session.execute(cls._with_names_select().where(Job.id == job_id))
        row = result.first()
        if row is None:
            return None
        return cls._row_to_names(row)

    @classmethod
    async def list_for_collection_with_names(
        cls,
        session: AsyncSession,
        collection_id: uuid.UUID,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JobWithNames]:
        """Return a collection's jobs (newest first), each joined to its display names.

        A ``limit`` bounds the page (``None`` = no bound, the legacy behaviour); ``offset`` skips rows
        for paging. The order is stable (created_at desc, then id) so paging never repeats/drops a row.
        """
        query = (
            cls._with_names_select()
            .where(Job.collection_id == collection_id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        result = await session.execute(query)
        return [cls._row_to_names(row) for row in result.all()]

    @classmethod
    async def list_active_with_names(cls, session: AsyncSession) -> list[JobWithNames]:
        """Return every RUNNING job joined to its display names — the fleet activity view."""
        result = await session.execute(
            cls._with_names_select()
            .where(Job.status == JobStatus.RUNNING)
            .order_by(Job.started_at.asc())
        )
        return [cls._row_to_names(row) for row in result.all()]

    @staticmethod
    def _order_clause(sort_by: str, descending: bool):  # type: ignore[no-untyped-def]
        """
        Build the ORDER BY tuple for the triage list — a sort field plus a stable id tie-break.

        Three sortable dimensions back the All-Jobs table: ``created`` (the monitoring default),
        ``duration`` (longest/shortest run — ``finished_at`` minus ``started_at``, or ``now`` minus
        ``started_at`` for a still-running job so it sorts by elapsed time), and ``status``. A
        still-pending job has no ``started_at``, so its duration is NULL and always sorts LAST under
        both directions (``nullslast``); every sort is tie-broken by ``id`` so paging is stable.

        Args:
            sort_by (str): "created" (default), "duration" or "status".
            descending (bool): True = DESC (newest / longest / z-a); False = ASC (FIFO / shortest / a-z).

        Returns:
            tuple: The (primary, tie-break) column expressions for ``order_by``.
        """
        if sort_by == "duration":
            elapsed = func.extract(
                "epoch", func.coalesce(Job.finished_at, func.now()) - Job.started_at
            )
            primary = elapsed.desc().nullslast() if descending else elapsed.asc().nullslast()
        elif sort_by == "status":
            primary = Job.status.desc() if descending else Job.status.asc()
        else:  # "created" — the default monitoring order.
            primary = Job.created_at.desc() if descending else Job.created_at.asc()
        tiebreak = Job.id.desc() if descending else Job.id.asc()
        return (primary, tiebreak)

    @classmethod
    async def list_with_names(
        cls,
        session: AsyncSession,
        collection_id: uuid.UUID | None = None,
        statuses: Sequence[JobStatus] | None = None,
        limit: int | None = None,
        offset: int = 0,
        newest_first: bool = True,
        *,
        sort_by: str = "created",
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[JobWithNames]:
        """
        Return one page of jobs (fleet-wide or scoped, fully triageable), joined to display names.

        The generalised read behind ``GET /jobs`` — a superset of ``list_for_collection_with_names``:
        an omitted ``collection_id`` lists across every collection (the "All Jobs" view), an omitted
        ``statuses`` lists every status. ``sort_by`` picks the dimension (created / duration / status)
        and ``newest_first`` its direction (DESC when True); the remaining filters (stage, error class,
        id search, created-date range) narrow the match through the shared ``_job_filters`` predicate,
        so the listed page and its ``count_jobs`` total always agree. Always tie-broken by ``id``.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.
            statuses (Sequence[JobStatus] | None): Restrict to these statuses, or None/empty for all.
            limit (int | None): Page size (None = no bound); ``offset`` skips rows for paging.
            offset (int): Rows to skip for paging.
            newest_first (bool): Sort direction — True = DESC (newest/longest first); False = ASC (FIFO).
            sort_by (str): The sort dimension — "created" (default), "duration" or "status".
            stage (str | None): Keep only jobs in this ``current_stage``.
            error_type (str | None): Keep only jobs with this structured failure class.
            search (str | None): Prefix-match the job id OR document id (triage search box).
            created_after (datetime | None): Keep jobs created at/after this instant (range start).
            created_before (datetime | None): Keep jobs created at/before this instant (range end).

        Returns:
            list[JobWithNames]: The page of jobs, each joined to its display names.
        """
        conditions = cls._job_filters(
            collection_id,
            statuses,
            stage=stage,
            error_type=error_type,
            search=search,
            created_after=created_after,
            created_before=created_before,
        )
        query = (
            cls._with_names_select()
            .where(*conditions)
            .order_by(*cls._order_clause(sort_by, newest_first))
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        result = await session.execute(query)
        return [cls._row_to_names(row) for row in result.all()]

    @classmethod
    async def count_jobs(
        cls,
        session: AsyncSession,
        collection_id: uuid.UUID | None = None,
        statuses: Sequence[JobStatus] | None = None,
        *,
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        """
        Count jobs matching the SAME triage filter set — the pager's total.

        Independent of limit/offset so the "All Jobs" pager knows the full match count. Uses the exact
        same predicate as ``list_with_names`` so the total always agrees with the listed page.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.
            statuses (Sequence[JobStatus] | None): Restrict to these statuses, or None/empty for all.
            stage (str | None): Keep only jobs in this ``current_stage``.
            error_type (str | None): Keep only jobs with this structured failure class.
            search (str | None): Prefix-match the job id OR document id.
            created_after (datetime | None): Keep jobs created at/after this instant.
            created_before (datetime | None): Keep jobs created at/before this instant.

        Returns:
            int: The number of matching jobs.
        """
        conditions = cls._job_filters(
            collection_id,
            statuses,
            stage=stage,
            error_type=error_type,
            search=search,
            created_after=created_after,
            created_before=created_before,
        )
        result = await session.execute(select(func.count()).select_from(Job).where(*conditions))
        return int(result.scalar_one())


__all__ = ["JobListingApi"]
