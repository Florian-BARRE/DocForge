# ====== Code Summary ======
# Result models of the job data-access APIs: a job joined to its display names (JobWithNames) and
# the raw aggregates behind the failure-breakdown panel and the trends sparklines.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass
from datetime import datetime

# ====== Internal Project Imports ======
from ...tables import Job, JobStatus


@dataclass(frozen=True)
class JobWithNames:
    """
    A job row joined to the human-readable names the fleet view shows alongside its ids.

    The jobs list is per-collection and small, so the display names (the document's filename, the
    collection's name) are resolved by a JOIN at read rather than denormalised onto the job row —
    this keeps names authoritative (a rename is reflected instantly) and needs no extra migration.

    Attributes:
        job (Job): The job row, verbatim.
        document_filename (str | None): The job's document filename (None if the document is gone).
        document_title (str | None): The document's metagen-generated title, when one was produced
            (None if the document is gone; empty string coalesced to None so the UI can fall back to
            the filename cleanly).
        collection_name (str | None): The job's collection name (None if the collection is gone).
        document_display_title (str | None): The document's DISPLAY title — the collection's
            ``title_field`` value when configured and set, else the parsed title (the
            DisplayTitleResolver rule); None if neither exists or the document is gone.
    """

    job: Job
    document_filename: str | None
    document_title: str | None
    collection_name: str | None
    document_display_title: str | None = None


@dataclass(frozen=True)
class FailureAggregates:
    """
    The raw grouped counts behind the failure-breakdown panel — three roll-ups over a window.

    Each grouping is ordered by descending count (the biggest cause first) and bounded to a top-N, so
    the "why is it breaking" panel shows the dominant causes rather than an unbounded long tail.

    Attributes:
        total (int): Total FAILED jobs matching the window (+ optional collection) filter.
        by_error_type (list[tuple[str | None, int]]): (error_type, count) — None = an unattributed
            failure (no structured exception class was recorded).
        by_stage (list[tuple[str | None, int]]): (current_stage, count) — the node the job died in;
            None = a failure with no recorded stage.
        by_collection (list[tuple[uuid.UUID, str | None, int]]): (collection_id, collection_name,
            count) — the collection name is None when the collection row is gone.
    """

    total: int
    by_error_type: list[tuple[str | None, int]]
    by_stage: list[tuple[str | None, int]]
    by_collection: list[tuple[uuid.UUID, str | None, int]]


@dataclass(frozen=True)
class TimeseriesAggregates:
    """
    The raw per-hour counts behind the trends sparklines — reconstructed purely from the job table.

    ``baseline`` is the instantaneous backlog (queued + running) at the window's START, so the per-
    bucket backlog can be rebuilt as ``baseline + cumulative(arrivals) - cumulative(completions)``
    without a Prometheus-style sample store. ``arrivals`` bucket by ``created_at``, ``completions``
    by ``finished_at`` (split by terminal status), so done/h and failed/h come straight from the rows.

    Attributes:
        baseline (int): Jobs created before the window that were still un-finished at its start.
        arrivals (list[tuple[datetime, int]]): (hour bucket, count created in that hour).
        completions (list[tuple[datetime, JobStatus, int]]): (hour bucket, terminal status, count
            finished in that hour) — only DONE/FAILED rows.
    """

    baseline: int
    arrivals: list[tuple[datetime, int]]
    completions: list[tuple[datetime, JobStatus, int]]


__all__ = ["JobWithNames", "FailureAggregates", "TimeseriesAggregates"]
